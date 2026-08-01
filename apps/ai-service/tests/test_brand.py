import unittest

from app.brand import omni_brand_text


class BrandTests(unittest.TestCase):
    def test_replaces_customer_facing_brand_terms(self):
        value = omni_brand_text("ShopeeVIP, ShopeeFood, SPayLater và Shopee Xu trên Shopee")
        self.assertEqual(value, "OmniVIP, OmniFood, OmniPayLater và Omni Xu trên Omni")


if __name__ == "__main__":
    unittest.main()
