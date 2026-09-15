from django.test import SimpleTestCase
from django.core.exceptions import ValidationError
from apps.core.phone import normalize_phone, PhoneField
from apps.communications.forms import ContactForm, ApplicationForm


class PhoneTests(SimpleTestCase):
    def test_tunisian_normalization(self):
        for number in ("20123456", "20 123 456", "+21620123456", "+216 20 123 456"):
            self.assertEqual(normalize_phone(number), "+21620123456")
        self.assertEqual(normalize_phone("74123456"), "+21674123456")

    def test_invalid_numbers(self):
        for number in ("abc", "22AA4455", "+216HELLO", "20123", "201234567", "+216", "00000000"):
            with self.subTest(number=number), self.assertRaises(ValidationError):
                normalize_phone(number)

    def test_widget_and_forms_validate_server_side(self):
        field = PhoneField()
        self.assertIn("Tunisie", field.label)
        self.assertIn("+216", field.label)
        self.assertEqual(field.widget.attrs["inputmode"], "numeric")
        for Form in (ContactForm, ApplicationForm):
            form = Form({"phone": "22AA4455"})
            self.assertFalse(form.is_valid())
            self.assertIn("phone", form.errors)
