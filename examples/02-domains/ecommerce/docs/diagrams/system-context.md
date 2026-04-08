# System Context Diagram (C4-inspired)

```mermaid
graph TD
    user_service("UserService")
    product_service("ProductService")
    order_service("OrderService")
    payment_service("PaymentService")
    shipping_service("ShippingService")
    order_service --> product_service
    order_service --> payment_service
    order_service --> shipping_service
```
