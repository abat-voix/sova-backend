from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Постраничный вывод: 50 записей по умолчанию, размер задаётся `page_size`."""

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
