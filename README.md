# Frolls

Virtual tabletop per giocare di ruolo fantasy online, compatibile 5e.

## Requisiti

- Python 3.12+
- Node.js 22+
- PostgreSQL 15+ in locale, con utente `frolls` (password `frolls`) e database `frolls_dev` e `frolls_test`:

  ```bash
  psql -U postgres -c "CREATE ROLE frolls LOGIN PASSWORD 'frolls' CREATEDB;" \
       -c "CREATE DATABASE frolls_dev OWNER frolls;" \
       -c "CREATE DATABASE frolls_test OWNER frolls;"
  ```

## Avvio in sviluppo

Dalla root del progetto:

```bash
npm run setup                                   # solo la prima volta
cd backend && .venv/Scripts/alembic upgrade head && cd ..   # crea/aggiorna le tabelle
npm run dev                                     # backend (8000) + frontend (5173)
```

Apri http://localhost:5173. Ogni scheda del browser è un giocatore diverso: aprine una come **Game Master** e una o più come **Giocatore** per provare la partita.

`Ctrl+C` ferma tutto. Nel log, `[api]` è il backend e `[web]` è il frontend.

## Comandi di gioco

| Azione | Come |
|---|---|
| Tirare dadi | scrivi in chat `d20`, `2d6+3`, `2d20kh1` (vantaggio), `4d6dl1`, `8d6!`, `5d10>8` |
| Tiro nel testo | `Colpisco per [[1d8+3]] danni` |
| Sussurro | `/w Nome messaggio`, `/w gm messaggio` |
| Tiro nascosto al GM | `/gr 1d20` |
| Azione / fuori gioco / narrazione | `/em`, `/ooc`, `/desc` (GM) |
| Ping | tieni premuto su un punto vuoto (GM + Maiusc: porta lì la vista di tutti) |
| Muovere la mappa | tasto centrale o destro, oppure Spazio + trascina |
| Zoom | rotellina |
| Strumenti | `V` seleziona, `H` mano, `R` righello, `D` matita, `T` testo |
| Token | doppio clic = impostazioni, tasto destro = menu, `Canc` elimina, frecce spostano, `Ctrl+C/V/D` copia/incolla/duplica, `Alt` durante il drag disattiva lo snap |

## Test

```bash
npm test        # pytest backend (DB frolls_test) + type-check frontend
npm run e2e     # con l'app avviata: due schede Chrome (GM + giocatore) provano le meccaniche
```

Lint del backend: `cd backend && .venv/Scripts/ruff check . && .venv/Scripts/ruff format --check .`

## Struttura

```
backend/
  app/
    main.py          # FastAPI app, lifespan, router
    config.py        # Settings da env (prefisso FROLLS_)
    db.py, models.py # SQLAlchemy async + modelli
    dice/            # Parser e motore dadi
    game/            # Server di gioco: protocollo, permessi, chat, stato
    api/             # REST: health, upload immagini
    ws/              # Endpoint WebSocket /ws/game
  migrations/        # Alembic
  tests/
frontend/
  src/
    App.svelte
    lib/canvas/      # Motore mappa PixiJS: griglia, misure, viste, input
    lib/components/  # UI Svelte
    lib/net/         # Client WebSocket e tipi del protocollo
    lib/state/       # GameStore e identità della scheda
docs/
  roll20-features.md # Specifica funzionale (riferimento clean-room)
e2e/
  game.mjs           # Collaudo nel browser
```

## Protocollo WebSocket

Endpoint unico `/ws/game`. Messaggi JSON con campo `type`; il primo messaggio del client è sempre `hello`. Le definizioni stanno in `backend/app/game/protocol.py` (client → server) e `frontend/src/lib/net/protocol.ts` (entrambe le direzioni): vanno tenute allineate.
