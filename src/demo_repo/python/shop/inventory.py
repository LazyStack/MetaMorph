"""Product catalogue and stock levels."""
from typing import Dict, List, Optional


class Product(object):
    def __init__(self, sku, name, price, qty):
        self.sku = sku
        self.name = name
        self.price = price
        self.qty = qty

    def label(self):
        return "%s (%s) - $%.2f" % (self.name, self.sku, self.price)

    def value(self):
        return self.price * self.qty


class PerishableProduct(Product):
    def __init__(self, sku, name, price, qty, days_left):
        super(PerishableProduct, self).__init__(sku, name, price, qty)
        self.days_left = days_left

    def label(self):
        base = super(PerishableProduct, self).label()
        return "%s [expires in %d days]" % (base, self.days_left)


class Inventory(object):
    def __init__(self):
        self._items: Dict[str, Product] = {}

    def add(self, product: Product) -> None:
        self._items[product.sku] = product

    def find(self, sku: str) -> Optional[Product]:
        return self._items.get(sku)

    def skus(self) -> List[str]:
        return sorted(self._items)

    def total_value(self):
        return sum(p.value() for p in self._items.values())

    def low_stock(self, threshold):
        return [p for p in self._items.values() if p.qty < threshold]
