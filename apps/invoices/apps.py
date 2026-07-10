from django.apps import AppConfig


class InvoicesConfig(AppConfig):
    name = 'apps.invoices'

    def ready(self):
        # Implicitly import the signals module here
        import apps.invoices.signals
