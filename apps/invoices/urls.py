from django.urls import path
from apps.invoices.views import InvoiceListView, InvoiceDetailView, InvoiceDownloadView,AdminPaymentInvoiceDetailView,AdminPaymentInvoiceDownloadView

urlpatterns = [
    path(
        "invoices/", 
        InvoiceListView.as_view(), 
        name="invoice-list"
    ),
    path(
        "invoices/<uuid:id>/", 
        InvoiceDetailView.as_view(), 
        name="invoice-detail"
    ),
    path(
        "invoices/<uuid:id>/download/", 
        InvoiceDownloadView.as_view(), 
        name="invoice-download"
    ),
    path(
        "admin/payments/<uuid:id>/invoice/",
        AdminPaymentInvoiceDetailView.as_view(),
        name="admin-payment-invoice-detail",
   ),
   path(
        "admin/payments/<uuid:id>/invoice/download/",
        AdminPaymentInvoiceDownloadView.as_view(),
        name="admin-payment-invoice-download",
),
]