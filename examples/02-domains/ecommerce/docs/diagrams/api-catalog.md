# API Catalog (Markdown table)

| Service | Method | Path | Entity |
|---------|--------|------|--------|
| UserService | GET | /api/v1/users | Ref('User', UNRESOLVED) |
| UserService | GET | /api/v1/users/:id | Ref('User', UNRESOLVED) |
| UserService | POST | /api/v1/users | Ref('User', UNRESOLVED) |
| UserService | PUT | /api/v1/users/:id | Ref('User', UNRESOLVED) |
| UserService | DELETE | /api/v1/users/:id | Ref('User', UNRESOLVED) |
| UserService | POST | /api/v1/register |  |
| UserService | POST | /api/v1/login |  |
| UserService | POST | /api/v1/logout |  |
| UserService | GET | /api/v1/me |  |
| UserService | PUT | /api/v1/me |  |
| UserService | PUT | /api/v1/me/password |  |
| UserService | POST | /api/v1/verify-email |  |
| UserService | POST | /api/v1/forgot-password |  |
| UserService | POST | /api/v1/reset-password |  |
| UserService | PUT | /api/v1/:id/status |  |
| UserService | GET | /api/v1/internal/:id |  |
| UserService | POST | /api/v1/internal/validate-session |  |
| ProductService | GET | /api/v1/products/products | Ref('Product', UNRESOLVED) |
| ProductService | GET | /api/v1/products/products/:id | Ref('Product', UNRESOLVED) |
| ProductService | POST | /api/v1/products/products | Ref('Product', UNRESOLVED) |
| ProductService | PUT | /api/v1/products/products/:id | Ref('Product', UNRESOLVED) |
| ProductService | DELETE | /api/v1/products/products/:id | Ref('Product', UNRESOLVED) |
| ProductService | GET | /api/v1/products/slug/:slug |  |
| ProductService | GET | /api/v1/products/search |  |
| ProductService | GET | /api/v1/products/category/:categoryId |  |
| ProductService | POST | /api/v1/products |  |
| ProductService | PUT | /api/v1/products/:id/inventory |  |
| ProductService | PUT | /api/v1/products/:id/publish |  |
| ProductService | POST | /api/v1/products/internal/check-availability |  |
| ProductService | POST | /api/v1/products/internal/reserve-inventory |  |
| ProductService | POST | /api/v1/products/internal/confirm-reservation |  |
| ProductService | POST | /api/v1/products/internal/release-reservation |  |
| ProductService | GET | /api/v1/products/internal/:id |  |
| ProductService | POST | /api/v1/products/internal/bulk |  |
| OrderService | GET | /api/v1/orders |  |
| OrderService | GET | /api/v1/orders/:id |  |
| OrderService | POST | /api/v1/orders |  |
| OrderService | PUT | /api/v1/orders/:id/cancel |  |
| OrderService | GET | /api/v1/orders/internal/:id |  |
| OrderService | POST | /api/v1/orders/:id/confirm-payment |  |
| OrderService | POST | /api/v1/orders/:id/update-shipment |  |
| PaymentService | GET | /api/v1/payments/payments/:id | Ref('Payment', UNRESOLVED) |
| PaymentService | GET | /api/v1/payments/order/:orderId |  |
| PaymentService | GET | /api/v1/payments/my-payments |  |
| PaymentService | POST | /api/v1/payments/process |  |
| PaymentService | POST | /api/v1/payments/:id/refund |  |
| PaymentService | POST | /api/v1/payments/webhook/stripe |  |
| ShippingService | GET | /api/v1/shipments/shipments/:id | Ref('Shipment', UNRESOLVED) |
| ShippingService | GET | /api/v1/shipments/order/:orderId |  |
| ShippingService | GET | /api/v1/shipments/track/:trackingNumber |  |
| ShippingService | POST | /api/v1/shipments |  |
| ShippingService | PUT | /api/v1/shipments/:id/status |  |
| ShippingService | POST | /api/v1/shipments/:id/events |  |
| ShippingService | POST | /api/v1/shipments/rates |  |
| ShippingService | POST | /api/v1/shipments/webhook/fedex |  |
