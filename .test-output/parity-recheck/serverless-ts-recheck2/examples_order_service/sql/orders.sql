CREATE TABLE "orders" (
    "id" UUID NOT NULL DEFAULT gen_random_uuid(),    "amount" NUMERIC NOT NULL,    "currency" TEXT NOT NULL,    "status" TEXT NOT NULL,    CONSTRAINT pk_orders PRIMARY KEY (id));
