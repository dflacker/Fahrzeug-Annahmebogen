# Fahrzeugannahme auf dem iPad – Online-Version

## Was enthalten ist
Ein Webformular mit Kamera-Upload, KI-Auslesen, Schadensfotos, Unterschrift und Drucken/PDF. Der API-Schlüssel bleibt ausschließlich auf dem Server.

## Einrichtung
1. Lege bei https://platform.openai.com ein separates API-Projekt an und erstelle einen API-Schlüssel. Setze in den **Projekt-Limits** ein monatliches Budget von höchstens 5 € Gegenwert in USD und aktiviere **Enforce a hard limit**, sofern verfügbar. Beachte: Auch diese Grenze kann durch verzögerte Abrechnung leicht überschritten werden.
2. Erstelle eine private GitHub-Ablage für diese Projektdateien (ohne Schlüssel).
3. Erstelle bei https://render.com einen Web Service aus dem GitHub-Repository, mit `render.yaml` als Blueprint oder manuell: Build `pip install -r requirements.txt`, Start `gunicorn --workers 1 --threads 4 --bind 0.0.0.0:$PORT server:app`.
4. Richte eine **dauerhafte PostgreSQL-Datenbank** ein (z. B. über einen geeigneten verwalteten Dienst). Setze deren Verbindungs-URL als geheime Umgebungsvariable `DATABASE_URL`. Ohne Datenbank werden Scans gesperrt. Kosten für Datenbank/Hosting sind nicht Teil des 5-€-API-Budgets.
5. Lege im Render-Dienst geheime Umgebungsvariablen `OPENAI_API_KEY`, `APP_PASSWORD` (langes zufälliges Passwort) und `DATABASE_URL` fest. `APP_USER` ist standardmäßig `werkstatt`. Schlüssel niemals in HTML oder GitHub eintragen.
6. Öffne die HTTPS-Adresse des Dienstes in Safari auf dem iPad und melde dich an. Über Teilen → „Zum Home-Bildschirm“ kannst du eine Verknüpfung anlegen.
7. Teste zunächst mit einem geschwärzten Fahrzeugschein. Alle erkannten Werte vor Übernahme prüfen.

## Wichtige Grenzen
- Die App reserviert pauschal 0,10 € je Scan und sperrt nach maximal 50 Versuchen pro UTC-Servermonat. **Das ist keine echte Verbrauchsmessung und keine Garantie für maximal 5 € API-Kosten.**
- Die API-Projektgrenze ist die zusätzliche Sicherung. Die Limits gelten für API-Kosten, **nicht** für Hosting oder Datenbank.
- Die Anmeldung ist eine einfache HTTP-Basic-Authentifizierung über HTTPS; für den dauerhaften Einsatz mit echten Kundendaten sollten Zugriffsschutz, Datenschutzinformationen, Auftragsverarbeitung, Löschkonzept und Sicherheitsprüfung professionell geprüft werden.
- Formularinhalte und Schadensbilder werden nicht auf dem Server als Akte gespeichert. Nach Schließen/Neuladen der Seite können Eingaben verloren gehen. Die fotografierten Fahrzeugscheine werden für die KI-Erkennung an OpenAI übertragen.
- Render Free schläft bei Inaktivität ein und ist nicht als produktive Lösung empfohlen. Prüfe Hosting-/Datenbankpreise und Datenschutzanforderungen.
