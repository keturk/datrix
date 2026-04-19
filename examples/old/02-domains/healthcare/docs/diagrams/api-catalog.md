# API Catalog (Markdown table)

| Service | Method | Path | Entity |
|---------|--------|------|--------|
| PatientService | GET | /api/v1/patients |  |
| PatientService | GET | /api/v1/patients/:id |  |
| PatientService | GET | /api/v1/patients/mrn/:mrn |  |
| PatientService | POST | /api/v1/patients |  |
| PatientService | PUT | /api/v1/patients/:id |  |
| PatientService | PUT | /api/v1/patients/:id/status |  |
| PatientService | GET | /api/v1/patients/internal/:id |  |
| PatientService | GET | /api/v1/patients/internal/mrn/:mrn |  |
| PatientService | POST | /api/v1/patients/internal/validate |  |
| PatientService | POST | /api/v1/patients/internal/bulk |  |
| AppointmentService | GET | /api/v1/appointments |  |
| AppointmentService | GET | /api/v1/appointments/:id |  |
| AppointmentService | POST | /api/v1/appointments |  |
| AppointmentService | PUT | /api/v1/appointments/:id |  |
| AppointmentService | PUT | /api/v1/appointments/:id/confirm |  |
| AppointmentService | PUT | /api/v1/appointments/:id/check-in |  |
| AppointmentService | PUT | /api/v1/appointments/:id/start |  |
| AppointmentService | PUT | /api/v1/appointments/:id/complete |  |
| AppointmentService | PUT | /api/v1/appointments/:id/cancel |  |
| AppointmentService | PUT | /api/v1/appointments/:id/no-show |  |
| AppointmentService | GET | /api/v1/appointments/patient/:patientId/upcoming |  |
| AppointmentService | GET | /api/v1/appointments/patient/:patientId/history |  |
| AppointmentService | GET | /api/v1/appointments/slots |  |
| AppointmentService | GET | /api/v1/appointments/internal/:id |  |
| AppointmentService | GET | /api/v1/appointments/internal/patient/:patientId |  |
| MedicalRecordService | GET | /api/v1/records |  |
| MedicalRecordService | GET | /api/v1/records/:id |  |
| MedicalRecordService | POST | /api/v1/records |  |
| MedicalRecordService | PUT | /api/v1/records/:id |  |
| MedicalRecordService | PUT | /api/v1/records/:id/finalize |  |
| MedicalRecordService | PUT | /api/v1/records/:id/amend |  |
| MedicalRecordService | PUT | /api/v1/records/:id/void |  |
| MedicalRecordService | POST | /api/v1/records/:id/attachments |  |
| MedicalRecordService | GET | /api/v1/records/:id/attachments/:attachmentId/download |  |
| MedicalRecordService | GET | /api/v1/records/prescriptions |  |
| MedicalRecordService | GET | /api/v1/records/prescriptions/:id |  |
| MedicalRecordService | POST | /api/v1/records/prescriptions |  |
| MedicalRecordService | POST | /api/v1/records/prescriptions/:id/refill |  |
| MedicalRecordService | PUT | /api/v1/records/prescriptions/:id/discontinue |  |
| MedicalRecordService | GET | /api/v1/records/patient/:patientId/history |  |
| MedicalRecordService | GET | /api/v1/records/internal/patient/:patientId |  |
| MedicalRecordService | POST | /api/v1/records/internal/from-appointment |  |
