# EasyList

Eine private, responsive Einkaufslisten-App auf Django 5.2 LTS. Sie verwendet serverseitige Django-Templates, HTMX für kleine Teilaktualisierungen, Bootstrap 5.3 und SortableJS ausschließlich für die Reihenfolge der Artikel.

## Enthalten

- Mehrere Listen je Benutzer: Titel, Datum, Artikel, Menge, Checkbox und Drag-and-drop-Reihenfolge
- Django-Standardauthentifizierung und Django-Admin
- REST-API unter `/api/v1/` mit TokenAuthentication und streng nutzerbezogenen Abfragen
- JSON-Import: `POST /api/v1/shopping-lists/import_json/`
- Gunicorn-Container für einen vorgeschalteten Nginx; PostgreSQL über `POSTGRES_*`-Variablen
- pytest-Tests für Modelle, Weboberfläche, API und Berechtigungen

## Lokale Entwicklung

Für den lokalen PostgreSQL-Dienst:

```sh
cp .env.example .env
# POSTGRES_PASSWORD und DJANGO_SECRET_KEY in .env setzen
docker compose up -d
```

Der Dienst ist ausschließlich auf `localhost:5432` erreichbar und speichert seine Daten im Docker-Volume `easylist_postgres`. Den Status prüfst du mit:

```sh
docker compose ps
```

Anschließend EasyList lokal starten:

```sh
cp .env.example .env
# DJANGO_SECRET_KEY in .env setzen
uv sync --all-groups
uv run --env-file .env python src/manage.py migrate
uv run --env-file .env python src/manage.py createsuperuser
uv run --env-file .env python src/manage.py runserver
```

`uv` lädt die lokale `.env`; Django benötigt dafür keine dotenv-Bibliothek. Die Anwendung ist danach unter `http://localhost:8000` verfügbar. Die Entwicklungs-Settings aktivieren bewusst `DEBUG`, damit Django die Quell-Staticfiles aus `src/shopping/static/` direkt ausliefert.

Ein Datenbank-Backup lässt sich in den laufenden lokalen PostgreSQL-Container importieren. Danach führt `migrate` fehlende Migrationen aus.

## Produktion: bestehender iqpp-Compose-Verbund

Das Image wird als `registry.iqpp.de/iqpp/easylist:latest` gebaut und lauscht intern auf Port `8000`. Es wird in den bestehenden `iqpp_prod`-Compose-Verbund aufgenommen. Compose lädt dort `./easylist/.env` mittels `env_file`; Django liest ausschließlich normale Umgebungsvariablen.

Die Produktionsdatei benötigt mindestens:

```dotenv
DJANGO_SECRET_KEY=<langer-zufälliger-wert>
DJANGO_ALLOWED_HOSTS=easylist.iqpp.de
DJANGO_CSRF_TRUSTED_ORIGINS=https://easylist.iqpp.de
POSTGRES_DB=easylist
POSTGRES_USER=<benutzer>
POSTGRES_PASSWORD=<passwort>
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

Der Container führt beim Start Migrationen und `collectstatic` aus. Das Ergebnis gehört in ein gemeinsames `easylist_static`-Volume, das Nginx unter `/static/` ausliefert. Das generierte Zielverzeichnis `src/staticfiles/` gehört nicht ins Repository. Für spätere Uploads kann unabhängig davon ein Media-Volume ergänzt werden.

## API

Token erzeugen, etwa über den Django-Admin oder die Shell:

```sh
uv run --env-file .env python src/manage.py drf_create_token <username>
```

Beispiel:

```sh
curl -H "Authorization: Token <token>" http://localhost:8000/api/v1/shopping-lists/
curl -X POST -H "Authorization: Token <token>" -H "Content-Type: application/json" \
  -d '{"lists":[{"title":"Pasta","date":"2026-10-30","items":[{"name":"Nudeln","quantity":"500 g"}]}]}' \
  http://localhost:8000/api/v1/shopping-lists/import_json/
```

Die API akzeptiert und liefert Listen mit eingebetteten Artikeln. Jeder Endpunkt ist auf den angemeldeten Benutzer begrenzt.

## Qualität

```sh
uv run pytest
```

Die Browser-Tests liegen getrennt in `e2e/` und werden automatisch von pytest ausgeführt. Einmalig Chromium installieren:

```sh
uv run playwright install chromium
```

Nur die Browser-Tests ausführen:

```sh
uv run pytest e2e
```

Die Datenstruktur ist bewusst klein gehalten: Eine spätere Rezeptfunktion kann als separates Modell mit einer Relation zu `ShoppingList` ergänzt werden.
