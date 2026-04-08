# System Context Diagram (C4-inspired)

```mermaid
graph TD
    student_service("StudentService")
    course_service("CourseService")
    enrollment_service("EnrollmentService")
    course_service --> student_service
    enrollment_service --> course_service
    enrollment_service --> student_service
```
