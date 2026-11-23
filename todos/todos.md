# Todos

- [ ] Klären, ob wir den Wochenplaner brauchen. Falls ja: um die Mahlzeiten Frühstück, Mittagessen, Abendessen und Snack erweitern (aktuell ein Rezept pro Tag).
- [ ] Bug: „Erledigte ausblenden“ funktioniert auf dem iPhone nicht, wenn die App über den Home-Bildschirm geöffnet ist. In Safari geht es.
  Vermutung: veraltetes JavaScript im Cache der Home-Bildschirm-App, weil die statischen Dateien keine Hash-Namen haben (kein `ManifestStaticFilesStorage`). Erst prüfen, ob es nach Neuinstallation der App geht, dann Cache-Busting einführen.
- [ ] Benutzerregistrierung hinzufügen, auch mit Anmeldung über Google und Apple.
- [ ] Listenanzeige überarbeiten, vor allem die Gruppierung.
- [ ] PWA oder native Apps (iOS/Android) in Betracht ziehen. Native Apps könnten die vorhandene REST-API nutzen.
  PWA (laut AGENTS.md nur bei klarem Produktbedarf). Hängt mit dem Cache-Bug der Home-Bildschirm-App zusammen: Ein Service Worker würde das Caching bewusst steuern.
- [ ] Offene Review-Punkte abarbeiten: `todos/django.txt` (2× hoch, 8× mittel, u. a. Validierung beim Schreiben und gleichzeitige Änderungen) und `todos/javascript.txt` (2 mittlere Bugs).
- [ ] Listen im Haushalt teilen: Mehrere Benutzer nutzen dieselbe Einkaufsliste (bisher gehören alle Daten genau einem Benutzer).
- [ ] Offline-Nutzung im Laden (schlechter Empfang). Wäre ein konkreter Produktgrund für die PWA.
- [ ] Portionen umrechnen: Zutatenmengen eines Rezepts an die gewünschte Personenzahl anpassen.
- [ ] Rezepte per URL importieren (schema.org/Recipe auslesen).
- [ ] Unterstützte Browser und Mindestversionen festlegen und dokumentieren (Hinweis aus der JS-Review).
