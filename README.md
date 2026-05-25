# Tietopankki

Streamlit-sovelluksen päätiedosto on `app.py`. Varsinainen sovelluslogiikka on tiedostossa `streamlit_app.py`.

## Paikallinen API-avain

Luo tai muokkaa paikallista tiedostoa `.streamlit/secrets.toml`:

```toml
OPENAI_API_KEY = "PASTE_YOUR_API_KEY_HERE"
```

Korvaa placeholder omalla OpenAI API -avaimellasi paikallisesti. Tiedosto on lisätty `.gitignore`-tiedostoon, joten sitä ei pidä committaa GitHubiin.

Käynnistä sovellus:

```bash
streamlit run app.py
```

## Streamlit Community Cloud

1. Vie projekti GitHub-repoon.
2. Avaa Streamlit Community Cloud ja luo uusi app GitHub-reposta.
3. Valitse päätiedostoksi `app.py`.
4. Avaa App Settings -> Secrets.
5. Lisää Secrets-kohtaan sama avain:

```toml
OPENAI_API_KEY = "PASTE_YOUR_API_KEY_HERE"
```

6. Deployaa sovellus.

## Projektirakenne

```text
project/
  .streamlit/
    secrets.toml
  app.py
  requirements.txt
```
