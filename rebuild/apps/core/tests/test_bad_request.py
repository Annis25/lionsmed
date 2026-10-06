"""Page 400 : elle doit dire quelle limite d'envoi a été dépassée, sans jamais afficher l'erreur brute."""
from django.core.exceptions import RequestDataTooBig, SuspiciousOperation, TooManyFilesSent
from django.test import RequestFactory, TestCase
from apps.core.views import bad_request


class BadRequestPageTests(TestCase):
    def page(self, exception, referer="http://testserver/espace/documents/deposer/"):
        request = RequestFactory().post("/espace/documents/deposer/", HTTP_REFERER=referer)
        response = bad_request(request, exception)
        self.assertEqual(response.status_code, 400)
        return response.content.decode()

    def test_photo_limit(self):
        html = self.page(RequestDataTooBig("trop lourd"))
        self.assertIn("5 Mo maximum par fichier", html)
        self.assertIn("réduisez la photo", html)
        self.assertIn('href="http://testserver/espace/documents/deposer/"', html)

    def test_document_limit_announced_by_the_upload_filter(self):
        exception = RequestDataTooBig("trop lourd")
        exception.document = True
        html = self.page(exception)
        self.assertIn("50 Mo maximum", html)
        self.assertNotIn("5 Mo maximum par fichier", html)
        self.assertNotIn("réduisez la photo", html)

    def test_too_many_files_and_other_refusals(self):
        self.assertIn("<h1>Trop de fichiers</h1>", self.page(TooManyFilesSent("trop")))
        html = self.page(SuspiciousOperation("autre"), referer="https://ailleurs.example/piege")
        self.assertIn("<h1>Demande refusée</h1>", html)
        self.assertNotIn("ailleurs.example", html)
        self.assertNotIn("Bad Request", html)
