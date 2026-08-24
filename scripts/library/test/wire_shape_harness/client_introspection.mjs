// Structural reading of the generated client tree, through the real
// TypeScript compiler API.
//
// Everything this module reports is read from the emitted `.ts` sources with
// a parser, never with a regex over their text: the route table comes from
// the generated route manifest's own array literal, each client method's HTTP
// verb and URL template come from the call expression in its body, and each
// method's declared response type comes from its `Observable<T>` return
// annotation resolved through the file's own import list. A hand-maintained
// parallel route list, or a text scrape that silently matches nothing, is the
// failure mode this exists to avoid.

import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import path from 'node:path';

// Sample values for branded string aliases whose FORMAT is load-bearing: the
// server parses these, so a generic string probe is rejected by validation
// before any response shape can be compared. An alias absent from this map is
// not a failure -- `brandedBaseType` unwraps it to its base primitive and the
// generic probe is used -- so this list only has to carry the formats that
// matter, never every brand the generator emits.
const BRANDED_SAMPLE_VALUES = new Map([
  ['Uuid', '11111111-2222-4333-8444-555555555555'],
  ['IsoDateTime', '2024-01-01T00:00:00Z'],
  ['WktGeometry', 'POINT(0 0)'],
  ['EwktGeography', 'SRID=4326;POINT(0 0)'],
  // An exact decimal carried as a string, from a backend that serializes
  // Decimal/Money that way rather than as an IEEE-754 JSON number.
  ['DecimalString', '19.99'],
]);

const SAMPLE_STRING = 'datrix-wire-shape-probe';
const SAMPLE_NUMBER = 1;
const SAMPLE_BOOLEAN = true;
const MAX_SYNTHESIS_DEPTH = 8;

/**
 * Load the pinned TypeScript compiler's JavaScript API.
 *
 * @param {{typescriptApiUrl: string}} env
 * @returns {Promise<object>}
 */
export async function loadTypescript(env) {
  const module = await import(env.typescriptApiUrl);
  return module.default ?? module;
}

async function parseSource(ts, file) {
  const text = await readFile(file, 'utf8');
  return ts.createSourceFile(file, text, ts.ScriptTarget.ES2022, true, ts.ScriptKind.TS);
}

/** Evaluate a literal expression node into a plain JavaScript value. */
function literalValue(ts, node) {
  if (ts.isStringLiteralLike(node)) {
    return node.text;
  }
  if (ts.isNumericLiteral(node)) {
    return Number(node.text);
  }
  if (node.kind === ts.SyntaxKind.TrueKeyword) {
    return true;
  }
  if (node.kind === ts.SyntaxKind.FalseKeyword) {
    return false;
  }
  if (node.kind === ts.SyntaxKind.NullKeyword) {
    return null;
  }
  if (ts.isArrayLiteralExpression(node)) {
    return node.elements.map((element) => literalValue(ts, element));
  }
  if (ts.isObjectLiteralExpression(node)) {
    const result = {};
    for (const property of node.properties) {
      if (!ts.isPropertyAssignment(property)) {
        throw new Error(
          `Unsupported object-literal member kind ${property.kind} while reading a generated ` +
            `literal. Expected a plain property assignment.`,
        );
      }
      if (ts.isComputedPropertyName(property.name)) {
        throw new Error(
          'Unsupported computed property name while reading a generated literal. Expected a ' +
            'plain identifier or string key.',
        );
      }
      result[property.name.text] = literalValue(ts, property.initializer);
    }
    return result;
  }
  throw new Error(
    `Unsupported literal node kind ${node.kind} while reading a generated literal. ` +
      `Expected a string, number, boolean, null, array, or object literal.`,
  );
}

/**
 * Read the generated route manifest.
 *
 * @param {object} ts
 * @param {string} manifestFile Absolute path to `routes/route-manifest.ts`.
 * @returns {Promise<Array<{routeKey: string, method: string, path: string, providers: string[], paramNames: string[]}>>}
 */
export async function readRouteManifest(ts, manifestFile) {
  const source = await parseSource(ts, manifestFile);
  let entries = null;
  for (const statement of source.statements) {
    if (!ts.isVariableStatement(statement)) {
      continue;
    }
    for (const declaration of statement.declarationList.declarations) {
      if (declaration.initializer === undefined) {
        continue;
      }
      const initializer = ts.isAsExpression(declaration.initializer)
        ? declaration.initializer.expression
        : declaration.initializer;
      if (ts.isArrayLiteralExpression(initializer)) {
        entries = literalValue(ts, initializer);
      }
    }
  }
  if (entries === null) {
    throw new Error(
      `No route array literal found in ${manifestFile}. Expected an exported array of route ` +
        `entries. Fix: regenerate the client tree -- the gate reads the routes from this file ` +
        `and never from a list of its own.`,
    );
  }
  return entries;
}

/** Map every imported type name in a source file to the file it comes from. */
function importedTypeOrigins(ts, source) {
  const origins = new Map();
  for (const statement of source.statements) {
    if (!ts.isImportDeclaration(statement) || statement.importClause === undefined) {
      continue;
    }
    const specifier = statement.moduleSpecifier;
    if (!ts.isStringLiteralLike(specifier)) {
      continue;
    }
    const bindings = statement.importClause.namedBindings;
    if (bindings === undefined || !ts.isNamedImports(bindings)) {
      continue;
    }
    for (const element of bindings.elements) {
      origins.set(element.name.text, specifier.text);
    }
  }
  return origins;
}

/** Resolve an extensionless relative module specifier to an absolute `.ts` path. */
function resolveModuleFile(fromFile, specifier) {
  const base = path.resolve(path.dirname(fromFile), specifier);
  for (const candidate of [`${base}.ts`, path.join(base, 'index.ts')]) {
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

/** Reconstruct the manifest-style route path from a generated URL template. */
function routePathFromTemplate(ts, node) {
  if (ts.isNoSubstitutionTemplateLiteral(node)) {
    return node.text;
  }
  if (!ts.isTemplateExpression(node)) {
    throw new Error(
      `Unsupported URL expression kind ${node.kind} in a generated client method. Expected a ` +
        `template literal built from the injected base URL and the route path.`,
    );
  }
  let reconstructed = node.head.text;
  for (const span of node.templateSpans) {
    reconstructed += placeholderFor(ts, span.expression);
    reconstructed += span.literal.text;
  }
  return reconstructed;
}

/** Render one template interpolation as either the base-URL prefix or a `:param` segment. */
function placeholderFor(ts, expression) {
  if (
    ts.isPropertyAccessExpression(expression) &&
    expression.expression.kind === ts.SyntaxKind.ThisKeyword
  ) {
    return '';
  }
  const argsMember = findArgsMember(ts, expression);
  if (argsMember === null) {
    throw new Error(
      `Could not identify the route parameter inside a generated URL interpolation. Expected ` +
        `an expression referencing 'args.<name>'.`,
    );
  }
  return `:${argsMember}`;
}

/** Find the first `args.<name>` property access inside an expression subtree. */
function findArgsMember(ts, node) {
  let found = null;
  const visit = (current) => {
    if (found !== null) {
      return;
    }
    if (
      ts.isPropertyAccessExpression(current) &&
      ts.isIdentifier(current.expression) &&
      current.expression.text === 'args'
    ) {
      found = current.name.text;
      return;
    }
    ts.forEachChild(current, visit);
  };
  visit(node);
  return found;
}

/** Extract the single type argument of an `Observable<T>` return annotation. */
function observableTypeArgument(ts, method) {
  const returnType = method.type;
  if (
    returnType === undefined ||
    !ts.isTypeReferenceNode(returnType) ||
    !ts.isIdentifier(returnType.typeName) ||
    returnType.typeName.text !== 'Observable' ||
    returnType.typeArguments === undefined ||
    returnType.typeArguments.length !== 1
  ) {
    throw new Error(
      `Generated client method '${method.name.getText()}' does not declare an ` +
        `Observable<T> return type. Expected exactly one type argument.`,
    );
  }
  return returnType.typeArguments[0];
}

/** Read the members of a generated method's single `args` object parameter. */
function argsMembers(ts, method) {
  if (method.parameters.length === 0) {
    return { members: [], hasDefault: true };
  }
  const parameter = method.parameters[0];
  const hasDefault = parameter.initializer !== undefined;
  if (parameter.type === undefined || !ts.isTypeLiteralNode(parameter.type)) {
    throw new Error(
      `Generated client method '${method.name.getText()}' does not declare an object-literal ` +
        `argument type. Expected 'args: { ... }'.`,
    );
  }
  const members = parameter.type.members.map((member) => ({
    name: member.name.getText(),
    optional: member.questionToken !== undefined,
    typeNode: member.type,
  }));
  return { members, hasDefault };
}

/** Read the wire name each query parameter is sent under, from `toHttpParams({...})`. */
function queryWireNames(ts, method) {
  const wireNames = new Map();
  const visit = (node) => {
    if (
      ts.isCallExpression(node) &&
      ts.isIdentifier(node.expression) &&
      node.expression.text === 'toHttpParams' &&
      node.arguments.length === 1 &&
      ts.isObjectLiteralExpression(node.arguments[0])
    ) {
      for (const property of node.arguments[0].properties) {
        if (!ts.isPropertyAssignment(property)) {
          continue;
        }
        const member = findArgsMember(ts, property.initializer);
        const wire = ts.isStringLiteralLike(property.name)
          ? property.name.text
          : property.name.getText();
        if (member !== null) {
          wireNames.set(member, wire);
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(method);
  return wireNames;
}

/** Find the `this.http.<verb>(...)` call a generated method issues. */
function httpCall(ts, method) {
  let call = null;
  const visit = (node) => {
    if (call !== null) {
      return;
    }
    if (
      ts.isCallExpression(node) &&
      ts.isPropertyAccessExpression(node.expression) &&
      ts.isPropertyAccessExpression(node.expression.expression) &&
      node.expression.expression.expression.kind === ts.SyntaxKind.ThisKeyword &&
      node.expression.expression.name.text === 'http'
    ) {
      call = { verb: node.expression.name.text, args: node.arguments };
      return;
    }
    ts.forEachChild(node, visit);
  };
  visit(method);
  if (call === null) {
    throw new Error(
      `Generated client method '${method.name.getText()}' issues no 'this.http.<verb>(...)' ` +
        `call. Expected exactly one.`,
    );
  }
  return call;
}

/**
 * Read every generated client class and its methods.
 *
 * @param {object} ts
 * @param {string[]} clientFiles Absolute paths of the emitted `*.client.ts` files.
 * @returns {Promise<Array<object>>}
 */
export async function readClientClasses(ts, clientFiles) {
  const classes = [];
  for (const file of clientFiles) {
    const source = await parseSource(ts, file);
    const origins = importedTypeOrigins(ts, source);
    for (const statement of source.statements) {
      if (!ts.isClassDeclaration(statement) || statement.name === undefined) {
        continue;
      }
      const methods = [];
      const introspectionFailures = [];
      for (const member of statement.members) {
        if (!ts.isMethodDeclaration(member)) {
          continue;
        }
        const name = member.name.getText();
        // A method whose shape this reader does not recognize is reported by
        // name, never allowed to abort the whole census: the remaining routes
        // still have to be checked, and "the harness threw" is a far worse
        // report than "this one method could not be read, and why".
        try {
          const call = httpCall(ts, member);
          const { members, hasDefault } = argsMembers(ts, member);
          methods.push({
            name,
            httpVerb: call.verb.toLowerCase(),
            routePath: routePathFromTemplate(ts, call.args[0]),
            responseTypeNode: observableTypeArgument(ts, member),
            argsMembers: members,
            argsHasDefault: hasDefault,
            queryWireNames: queryWireNames(ts, member),
            sourceFile: file,
            importOrigins: origins,
          });
        } catch (error) {
          introspectionFailures.push(
            `${statement.name.text}.${name}: ${error instanceof Error ? error.message : String(error)}`,
          );
        }
      }
      classes.push({ file, className: statement.name.text, methods, introspectionFailures });
    }
  }
  return classes;
}

/**
 * Render a method's declared response type as a self-contained type expression.
 *
 * The comparator compiles its probes outside the client tree, so a bare
 * `OrderResponse` there means nothing. Every named type in the annotation is
 * therefore rewritten as a numbered placeholder over the file that declares
 * it, which the comparator turns into an `import(...)` type once it knows
 * where its own probes live. Array and generic annotations survive that
 * rewrite intact -- a list-returning route is as much a wire shape as a
 * single-object one.
 *
 * @returns {{kind: 'untyped'} | {kind: 'declared', expression: string, typeFiles: string[]}
 *   | {kind: 'unresolved', reason: string}}
 */
export function renderResponseTypeExpression(ts, method) {
  const node = method.responseTypeNode;
  if (node.kind === ts.SyntaxKind.UnknownKeyword || node.kind === ts.SyntaxKind.AnyKeyword) {
    return { kind: 'untyped' };
  }
  /** @type {string[]} */
  const typeFiles = [];
  /** @type {string[]} */
  const problems = [];

  const placeholderFor = (typeName) => {
    const specifier = method.importOrigins.get(typeName);
    if (specifier === undefined) {
      problems.push(`'${typeName}' is not imported by ${method.sourceFile}`);
      return 'unknown';
    }
    const typeFile = resolveModuleFile(method.sourceFile, specifier);
    if (typeFile === null) {
      problems.push(`'${typeName}' imported from '${specifier}' resolves to no emitted file`);
      return 'unknown';
    }
    const index = typeFiles.indexOf(typeFile);
    return `@{${index === -1 ? typeFiles.push(typeFile) - 1 : index}}.${typeName}`;
  };

  const render = (current) => {
    if (ts.isArrayTypeNode(current)) {
      return `(${render(current.elementType)})[]`;
    }
    if (ts.isUnionTypeNode(current)) {
      return current.types.map((member) => `(${render(member)})`).join(' | ');
    }
    if (ts.isParenthesizedTypeNode(current)) {
      return `(${render(current.type)})`;
    }
    if (ts.isLiteralTypeNode(current)) {
      return current.getText();
    }
    switch (current.kind) {
      case ts.SyntaxKind.StringKeyword:
      case ts.SyntaxKind.NumberKeyword:
      case ts.SyntaxKind.BooleanKeyword:
      case ts.SyntaxKind.UnknownKeyword:
      case ts.SyntaxKind.AnyKeyword:
      case ts.SyntaxKind.NullKeyword:
      case ts.SyntaxKind.UndefinedKeyword:
      case ts.SyntaxKind.VoidKeyword:
        return current.getText();
      default:
        break;
    }
    if (ts.isTypeReferenceNode(current) && ts.isIdentifier(current.typeName)) {
      const name = current.typeName.text;
      const args = current.typeArguments;
      if (name === 'Array' && args?.length === 1) {
        return `(${render(args[0])})[]`;
      }
      const head = placeholderFor(name);
      return args === undefined || args.length === 0
        ? head
        : `${head}<${args.map((arg) => render(arg)).join(', ')}>`;
    }
    problems.push(`node kind ${current.kind} (${current.getText()})`);
    return 'unknown';
  };

  const expression = render(node);
  if (problems.length > 0) {
    return {
      kind: 'unresolved',
      reason:
        `the declared response type of '${method.name}' cannot be resolved: ` +
        problems.join('; '),
    };
  }
  return { kind: 'declared', expression, typeFiles };
}

/** Find an interface, type-alias, or enum declaration by name inside a parsed source. */
function findDeclaration(ts, source, name) {
  for (const statement of source.statements) {
    if (
      (ts.isInterfaceDeclaration(statement) ||
        ts.isTypeAliasDeclaration(statement) ||
        ts.isEnumDeclaration(statement)) &&
      statement.name.text === name
    ) {
      return statement;
    }
  }
  return null;
}

/**
 * Synthesize a value conforming to a declared contract type.
 *
 * Produces a value the backend can accept where the type says what a valid
 * value looks like, and reports the type it could not construct otherwise --
 * never a silent placeholder.
 *
 * @returns {Promise<{ok: true, value: unknown} | {ok: false, reason: string}>}
 */
export async function synthesizeValue(ts, typeNode, contextFile, origins, depth = 0) {
  if (depth > MAX_SYNTHESIS_DEPTH) {
    return { ok: false, reason: `type nesting deeper than ${MAX_SYNTHESIS_DEPTH} levels` };
  }
  if (ts.isUnionTypeNode(typeNode)) {
    for (const member of typeNode.types) {
      if (
        member.kind === ts.SyntaxKind.NullKeyword ||
        member.kind === ts.SyntaxKind.UndefinedKeyword
      ) {
        continue;
      }
      return synthesizeValue(ts, member, contextFile, origins, depth);
    }
    return { ok: false, reason: 'a union of only null/undefined' };
  }
  if (ts.isLiteralTypeNode(typeNode)) {
    if (ts.isStringLiteralLike(typeNode.literal)) {
      return { ok: true, value: typeNode.literal.text };
    }
    if (ts.isNumericLiteral(typeNode.literal)) {
      return { ok: true, value: Number(typeNode.literal.text) };
    }
    return { ok: false, reason: `literal type ${typeNode.getText()}` };
  }
  if (ts.isArrayTypeNode(typeNode)) {
    const element = await synthesizeValue(ts, typeNode.elementType, contextFile, origins, depth + 1);
    return element.ok ? { ok: true, value: [element.value] } : element;
  }
  if (ts.isTypeLiteralNode(typeNode)) {
    return synthesizeMembers(ts, typeNode.members, contextFile, origins, depth);
  }
  switch (typeNode.kind) {
    case ts.SyntaxKind.StringKeyword:
      return { ok: true, value: SAMPLE_STRING };
    case ts.SyntaxKind.NumberKeyword:
      return { ok: true, value: SAMPLE_NUMBER };
    case ts.SyntaxKind.BooleanKeyword:
      return { ok: true, value: SAMPLE_BOOLEAN };
    case ts.SyntaxKind.UnknownKeyword:
    case ts.SyntaxKind.AnyKeyword:
      // The renderer emits `unknown` where the DSL declares a free-form JSON
      // value. Every JSON value inhabits it, so an empty object is a
      // conforming member of the declared type -- not a stand-in for a type
      // the harness failed to map.
      return { ok: true, value: {} };
    default:
      break;
  }
  if (!ts.isTypeReferenceNode(typeNode) || !ts.isIdentifier(typeNode.typeName)) {
    return { ok: false, reason: `type node kind ${typeNode.kind} (${typeNode.getText()})` };
  }
  const name = typeNode.typeName.text;
  if (name === 'Array' && typeNode.typeArguments?.length === 1) {
    const element = await synthesizeValue(
      ts,
      typeNode.typeArguments[0],
      contextFile,
      origins,
      depth + 1,
    );
    return element.ok ? { ok: true, value: [element.value] } : element;
  }
  const branded = BRANDED_SAMPLE_VALUES.get(name);
  if (branded !== undefined) {
    return { ok: true, value: branded };
  }
  const specifier = origins.get(name);
  if (specifier === undefined) {
    return { ok: false, reason: `type '${name}' is not imported by ${contextFile}` };
  }
  const typeFile = resolveModuleFile(contextFile, specifier);
  if (typeFile === null) {
    return { ok: false, reason: `type '${name}' resolves to no emitted file` };
  }
  const source = await parseSource(ts, typeFile);
  const declaration = findDeclaration(ts, source, name);
  if (declaration === null) {
    return { ok: false, reason: `type '${name}' is not declared in ${typeFile}` };
  }
  const nestedOrigins = importedTypeOrigins(ts, source);
  if (ts.isEnumDeclaration(declaration)) {
    const first = declaration.members[0];
    if (first === undefined) {
      return { ok: false, reason: `enum '${name}' declares no members` };
    }
    if (first.initializer === undefined) {
      return { ok: false, reason: `enum member '${name}.${first.name.getText()}' has no value` };
    }
    return { ok: true, value: literalValue(ts, first.initializer) };
  }
  if (ts.isInterfaceDeclaration(declaration)) {
    return synthesizeMembers(ts, declaration.members, typeFile, nestedOrigins, depth);
  }
  const unbranded = brandedBaseType(ts, declaration.type);
  if (unbranded !== null) {
    return synthesizeValue(ts, unbranded, typeFile, nestedOrigins, depth + 1);
  }
  return synthesizeValue(ts, declaration.type, typeFile, nestedOrigins, depth + 1);
}

/**
 * The base type of a branded alias -- `Brand<string, 'Uuid'>` -> the `string`
 * node -- or `null` when this is not a branded alias.
 *
 * The generator brands every alias whose wire form is a string but whose
 * meaning is not "any string" (`Uuid`, `IsoDateTime`, `WktGeometry`,
 * `EwktGeography`, `DecimalString`). The brand helper itself is a local,
 * un-exported type in the emitted `branded.ts`, so following the alias
 * naively dies on "type 'Brand' is not imported" -- which is what happened
 * the first time a branded alias appeared in a REQUEST BODY rather than a
 * path parameter, and which would have happened again for every future one.
 * Recognising the shape rather than the NAME keeps this working whatever the
 * generator brands next.
 *
 * `BRANDED_SAMPLE_VALUES` is still consulted first, and still matters: it
 * carries the aliases whose FORMAT is load-bearing, where a generic string
 * probe would be rejected by the server's own validation before the response
 * shape could be compared at all.
 *
 * @param {object} ts The TypeScript module.
 * @param {object} node The alias's right-hand-side type node.
 * @returns {object|null} The base type node, or null.
 */
function brandedBaseType(ts, node) {
  if (node === undefined || !ts.isIntersectionTypeNode(node)) {
    return null;
  }
  const [base, ...rest] = node.types;
  if (base === undefined || rest.length === 0) {
    return null;
  }
  const carriesBrandMember = rest.some(
    (member) =>
      ts.isTypeLiteralNode(member) &&
      member.members.every((entry) => ts.isPropertySignature(entry)),
  );
  return carriesBrandMember ? base : null;
}

async function synthesizeMembers(ts, members, contextFile, origins, depth) {
  const value = {};
  for (const member of members) {
    if (!ts.isPropertySignature(member) || member.type === undefined) {
      continue;
    }
    if (member.questionToken !== undefined) {
      continue;
    }
    const synthesized = await synthesizeValue(ts, member.type, contextFile, origins, depth + 1);
    if (!synthesized.ok) {
      return {
        ok: false,
        reason: `property '${member.name.getText()}': ${synthesized.reason}`,
      };
    }
    value[member.name.getText()] = synthesized.value;
  }
  return { ok: true, value };
}
