package library_book_service.cqrs.views;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.OffsetDateTime;
import java.util.UUID;
import library_book_service.enums.BookStatus;

/**
 * Read-side view model for BookCatalogView.
 *
 * <p>Updated by projections, not by direct writes. Optimized for query performance. Auto-generated
 * by datrix-codegen-java. Do not edit manually.
 */
@Entity
@Table(name = "book_catalog_views")
public class BookCatalogView {

  @Id
  @Column(name = "id", columnDefinition = "uuid", nullable = false)
  private UUID id;

  @Column(name = "title", columnDefinition = "text", nullable = false)
  private String title;

  @Column(name = "author", columnDefinition = "text", nullable = false)
  private String author;

  @Column(name = "publication_year", columnDefinition = "integer", nullable = false)
  private Integer publication_year;

  @Column(name = "status", columnDefinition = "varchar(255)", nullable = false)
  private BookStatus status;

  @Column(name = "last_updated", columnDefinition = "timestamptz", nullable = false)
  private OffsetDateTime last_updated;

  public UUID getId() {
    return this.id;
  }

  public void setId(UUID id) {
    this.id = id;
  }

  public String getTitle() {
    return this.title;
  }

  public void setTitle(String title) {
    this.title = title;
  }

  public String getAuthor() {
    return this.author;
  }

  public void setAuthor(String author) {
    this.author = author;
  }

  public Integer getPublication_year() {
    return this.publication_year;
  }

  public void setPublication_year(Integer publication_year) {
    this.publication_year = publication_year;
  }

  public BookStatus getStatus() {
    return this.status;
  }

  public void setStatus(BookStatus status) {
    this.status = status;
  }

  public OffsetDateTime getLast_updated() {
    return this.last_updated;
  }

  public void setLast_updated(OffsetDateTime last_updated) {
    this.last_updated = last_updated;
  }
}
