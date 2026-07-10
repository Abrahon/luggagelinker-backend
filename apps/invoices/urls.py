from django.urls import path
from apps.invoices.views import InvoiceListView, InvoiceDetailView, InvoiceDownloadView

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
]