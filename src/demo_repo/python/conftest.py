import pytest

from shop.inventory import Inventory, PerishableProduct, Product


@pytest.fixture
def inventory():
    inv = Inventory()
    inv.add(Product("A1", "Anchor", 12.5, 4))
    inv.add(Product("B2", "Bolt", 0.25, 11))
    inv.add(PerishableProduct("M3", "Milk", 1.2, 7, days_left=3))
    return inv
