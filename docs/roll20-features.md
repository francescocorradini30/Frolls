# Roll20: specifica funzionale per Frolls

> Documento di specifica **clean-room**. Descrive solo il **comportamento** di Roll20 osservabile da fonti pubbliche (wiki della community, Help Center, blog, forum, recensioni). Nessun codice Roll20 è stato letto o copiato. Ogni sezione dice cosa fa la funzione, come si comporta per l'utente, chi può usarla (GM o giocatore), quali dati servono, i casi limite e le lamentele note che Frolls deve risolvere.
>
> Ricerca del 2026-10-18. Il wiki Roll20 e l'Help Center bloccano l'accesso automatico, quindi le pagine del wiki sono state lette da copie del Wayback Machine (revisioni 2022-2025). Roll20 ha rilasciato il nuovo motore "Jumpgate" a gennaio 2025: dove il comportamento nuovo è diverso da quello legacy, lo indico.
>
> **Esclusi per decisione utente** (solo elenco finale): voce/video, audio/jukebox, fog of war, luci dinamiche, visione/linea di vista.

## Legenda

- **GM**: Game Master. In Roll20 esistono tre ruoli: **Creatore** (uno solo, possiede la partita, i suoi abbonamenti sbloccano le funzioni), **GM** (promosso dal Creatore, può essere più d'uno), **Giocatore**.
- **"Controllato da"**: elenco di giocatori (o "Tutti i giocatori") con permesso di controllo su un token o personaggio.
- **[Frolls+]**: miglioria consigliata rispetto a Roll20, motivata da una lamentela documentata.
- **[Decisione Frolls]**: punto in cui Roll20 non definisce il comportamento, o lo definisce male, e Frolls deve scegliere.

---

## 1. Account, partite e ruoli

### Cosa fa
Un account crea partite ("Game"/"Campaign"). Ogni partita ha una pagina **Dettagli partita** fuori dal tavolo virtuale (VTT), con giocatori, impostazioni, archivio chat, forum privato e pulsante "Avvia partita".

### Comportamento
- **Creazione partita**: nome, scelta facoltativa del template di scheda (o "Nessuno"), tag. Per Frolls il template sarà sempre "5e (SRD)".
- **Invito**: il pulsante "Invita giocatori" mostra un **link di invito unico** da copiare e permette inviti via email con lista degli inviti in sospeso. Chiunque abbia il link può entrare. Lo può condividere qualsiasi GM.
- **Espulsione**: "Espelli dalla partita" rimuove il giocatore **e rigenera il link di invito**, così il vecchio link smette di funzionare. Per far rientrare qualcuno serve il link nuovo.
- **Promozione**: solo il Creatore può fare "Promuovi a GM" o "Retrocedi a giocatore" passando sull'icona del giocatore. Il GM ha un'etichetta "GM" blu sull'avatar.
- **Più GM** possono essere collegati insieme.
- **Entra come giocatore**: un GM può fare "Rientra come giocatore" (perde gli strumenti GM fino a "Rientra come GM") per vedere ciò che vede un giocatore. C'è un link apposito con `?desiredrole=player`.
- **Lascia la partita**: unica opzione delle impostazioni disponibile ai giocatori.
- **Info partita**: sistema giocato, data e ora della prossima sessione (convertita nel fuso dell'utente; solo orologio a 12 ore, lamentato), descrizione in Markdown, icona.
- **Copia partita** (Creatore): sceglie cosa copiare: giocatori e impostazioni (macro incluse), pagine, mazzi e tabelle, log chat, journal, playlist, forum. Il template di scheda torna a "Nessuno" e va riscelto (bug di UX).
- **Elimina partita**: con conferma, irreversibile.
- **Rollback** (solo Pro): uno snapshot al giorno tra le 4 e le 6 PST, conservato per 7 giorni; si sceglie la data e si ripristina.
- **Forum della partita**: discussioni con thread e risposte; GM e Creatore possono mettere in evidenza, affondare, eliminare e ripristinare.
- **Cerco giocatori (LFG)**: annuncio pubblico della partita in una directory (fuori dallo scope iniziale).

### Dati
`User(id, username, display_name, avatar, color)`, `Game(id, name, creator_id, sheet_template, description_md, next_session_at, tags, invite_token, created_at)`, `GameMember(game_id, user_id, role: creator|gm|player, joined_at)`, `Invite(email, status)`.

### Casi limite
- Ruoli per partita, non per account: lo stesso utente è GM in una partita e giocatore in un'altra.
- I nomi dei giocatori compaiono nei menu dei permessi solo **dopo** che sono entrati almeno una volta nella partita.
- Il Creatore non può essere retrocesso.

### Lamentele e cosa fare meglio
- [Frolls+] Data e ora della sessione con orologio a 24 ore e fuso esplicito.
- [Frolls+] Rollback per tutti, non a pagamento, e più granulare: Frolls ha già un log di eventi delta e può offrire uno storico per oggetto.
- [Frolls+] La copia della partita deve conservare il template di scheda.
- Sicurezza: nel dicembre 2018 Roll20 ha subito una violazione con circa 4 milioni di account (email, IP, hash bcrypt, ultime 4 cifre della carta) ([HIBP](https://haveibeenpwned.com/Breach/Roll20)). Frolls: minimizzare i dati personali, nessun dato di pagamento in casa.

> Nota: per decisione utente auth e account si fanno **per ultimi**. Fino ad allora esiste una sola partita persistente e il ruolo si sceglie all'ingresso.

---

## 2. Struttura dell'interfaccia

- **Tabletop** (centro): canvas della pagina corrente.
- **Toolbar** (sinistra), dall'alto: Seleziona/Sposta (con modalità Pan), Layer (solo GM), Strumenti di disegno, Testo (separato dopo il redesign), Effetti FX, Zoom, Misura, Strumento Posiziona (luci/porte/finestre, escluso), Fog of War (escluso), Turn Tracker (solo GM), Dadi (GUI), Aiuto. Dopo il redesign del 2023-2024 i layer stanno in fondo alla toolbar (ordine: GM, Luci, Mappa, più Primo piano dal 2025).
- **Page Toolbar** (in alto, solo GM): elenco delle pagine e Player Ribbon.
- **Sidebar** (destra, ridimensionabile), schede: Chat, Art Library (solo GM), Journal, Compendium, Jukebox (escluso), Collezioni (macro, mazzi, tabelle), Impostazioni personali.
- **Area giocatori** (in basso a sinistra): avatar di ogni giocatore connesso con nome e colore. Ci si possono trascinare sopra le carte (per darle in mano), gli handout (per mostrarli) e i giocatori sulle pagine (split party).
- **Macro Quick Bar** (in basso): pulsanti macro del singolo utente.
- **Barra Token Actions** (in alto): appare quando un token è selezionato.
- **Popout**: chat, schede personaggio e handout si possono aprire in una finestra separata. In popout alcune funzioni della scheda (drag dei pulsanti, sezioni ripetute, Charactermancer) non funzionano: è una lamentela nota.
- **Modalità scura** (dal 2022).

[Frolls+] Interfaccia separata tra GM e giocatore: era uno degli obiettivi dichiarati del redesign Roll20 ([wiki](https://wiki.roll20.net/Toolbar_%26_Layers_Redesign)). Usabile anche su tablet: Owlbear Rodeo è apprezzato per questo.

---

## 3. Pagine (mappe)

### Cosa fa
Una partita contiene più **pagine** (scene, mappe, incontri). Si vede una pagina alla volta. Il GM può stare su una pagina diversa da quella dei giocatori, ad esempio per preparare la scena successiva.

### Page Toolbar (solo GM)
- Elenco orizzontale di miniature; si scorre con Maiusc+rotella.
- **Crea nuova pagina**; **rinomina** cliccando sul nome (Invio per salvare).
- **Riordina** con il drag & drop.
- Al passaggio del mouse compaiono **Impostazioni** (ingranaggio) e **Duplica**.
- **Duplica pagina**: copia impostazioni **e** contenuto. La copia completa esiste solo dal dicembre 2020; prima serviva uno script.
- **Cartelle di pagine** (da ottobre 2023, molto richieste).
- **Icona della pagina** = l'immagine più grande presente sulla pagina. Per cambiarla il trucco è un'immagine enorme mandata in fondo: pessima UX. [Frolls+] Miniatura scelta esplicitamente oppure generata automaticamente dalla mappa.
- **Archivia pagina**: la nasconde in un'area "Archiviate" a destra, da cui si ripristina. Le pagine archiviate però **si caricano comunque all'avvio** e non migliorano le prestazioni ([wiki Archiving](https://wiki.roll20.net/Archiving)). [Frolls+] Caricamento lazy: archiviate e non viste non si caricano.
- **Elimina pagina**: in fondo alle impostazioni. **Non si può eliminare** la pagina dove si trova il Player Ribbon né quella che si sta guardando.

### Player Ribbon e split party
- Il **Player Ribbon** (segnalibro rosso) indica la pagina dei giocatori. Il GM lo **trascina** su un'altra pagina e tutti i giocatori vengono spostati lì. Il GM **non** si sposta: per andarci deve fare doppio clic sulla pagina.
- **Split the Party**: il GM trascina l'avatar di un giocatore dall'area giocatori su una pagina. Compare un'iconcina del giocatore su quella pagina. Trascinandola su un'altra pagina lo si sposta; trascinandola **sul Ribbon** (non basta la stessa pagina) il giocatore torna al gruppo.
- **Define Party / Place Party** (Jumpgate, agosto 2025): i personaggi hanno la proprietà "Membro del party", attivabile dal menu contestuale o dalla scheda. "Place Party" porta in due clic tutti i token del party in un punto di una pagina, sposta il Ribbon e centra la vista ([BoLS](https://www.belloflostsouls.net/2025/08/roll20-unleashes-powerful-new-party-tools-after-recent-jumpgate-upgrades.html), [forum](https://app.roll20.net/forum/post/12465889/gm-time-save-alert-party-tools-are-here)).
- **Spostare token tra pagine**: Ctrl+C sulla selezione, si cambia pagina, Ctrl+V. Il punto di incolla è l'ultimo clic sul tavolo.
- Al caricamento di una pagina la vista parte dall'**angolo in alto a sinistra**: è una lamentela, il GM deve usare il pull-ping. [Frolls+] Vista iniziale centrata sui token del giocatore, oppure un punto di partenza salvato per pagina.

### Impostazioni pagina (solo GM)
I valori di default delle nuove pagine si impostano nelle Impostazioni partita.
- **Nome**.
- **Dimensioni**: larghezza e altezza in unità da 70 px (oppure in pixel, convertiti). Base: **70 px = 1 cella = 1 pollice al 100%**. Jumpgate permette di fare pan oltre i bordi.
- **Colore di sfondo** (selettore con esadecimale).
- **Scala**: quanto vale una cella (default **5**), unità **ft, m, km, mi** o personalizzata. Senza griglia la scala vale ogni 70 px.
- **Griglia**: attiva o disattiva (disattivarla toglie anche lo snap); tipo **quadrata, esagonale orizzontale, esagonale verticale** (in Roll20 c'è anche "isometrica" nelle versioni recenti, da verificare); **dimensione della cella** come moltiplicatore (0.5 = 35 px) o in pixel; **colore** e **opacità** delle linee (opacità 0 = linee invisibili ma snap attivo); **etichette** delle celle (solo esagoni); **misura delle diagonali** (vedi §5).
- **Play on load**: traccia audio (esclusa).
- **Archivia** ed **Elimina**.
- Le sezioni Fog of War e Luci dinamiche sono escluse.

### Dati
`Page(id, game_id, name, folder_id, order, width_units, height_units, bg_color, scale_number, scale_unit, grid_type, cell_size, grid_color, grid_opacity, grid_labels, diagonal_rule, archived, thumbnail_asset_id)`, `Game.player_page_id`, `PlayerPageOverride(user_id, page_id)`, `Character.is_party_member`.

### Casi limite
- Un giocatore in split party resta sulla sua pagina anche quando il Ribbon si sposta.
- Il turn tracker è globale tra le pagine (vedi §10).
- Il Ribbon non può puntare a una pagina archiviata.

---

## 4. Layer

| Layer | Chi lo vede | Uso | Note |
|---|---|---|---|
| **Mappa e sfondo** | tutti | mappe, arredi statici, token di nemici sconfitti | quando è attivo, i token degli altri layer sono grigi e non selezionabili |
| **Oggetti e token** | tutti | token e oggetti con cui si gioca; solo qui ci sono menu radiale, barre e marker | i giocatori sono **sempre** su questo layer e non possono cambiarlo |
| **GM Info Overlay** | solo GM | note, trappole, token nascosti | gli oggetti appaiono **sempre grigi e semitrasparenti** al GM per ricordargli che sono nascosti; selezionabili solo con il layer attivo |
| **Primo piano** (giugno 2025) | tutti | tetti, chiome di alberi, meteo sopra i token | richiesto per anni ([wiki](https://wiki.roll20.net/Foreground_Layer)) |
| Luci dinamiche / Muri | solo GM | **escluso** | |

### Comportamento
- Si cambia layer dalla toolbar o con **Ctrl+M** (mappa), **Ctrl+O** (oggetti), **Ctrl+K** (GM).
- Per **spostare la selezione** di layer: tasto destro, Layer, nome del layer, oppure **Ctrl+Maiusc+M/O/K** (cambia layer attivo e sposta gli oggetti).
- Un oggetto nuovo nasce sul **layer attivo**.
- Caso d'uso tipico: nemici preparati sul layer GM e spostati sul layer oggetti per l'imboscata.
- I disegni e i testi seguono le stesse regole dei layer.

### Lamentele
- [Frolls+] Rivelare un gruppo di token del layer GM in un clic ("incontri"): oggi serve lo script EncounterHelper.
- [Frolls+] Layer bloccabili, così da non spostare per errore la mappa.

---

## 5. Griglia, scala e misura

### Snap
- Con la griglia attiva lo snap vale per **spostamento, ridimensionamento e rotazione**. **Alt** tenuto premuto lo disattiva temporaneamente.
- Su griglia quadrata il token si aggancia all'**angolo** (in Roll20 "in basso a destra" della cella), su esagonale al **centro** dell'esagono.
- Rotazione con snap: passi di **45°** su griglia quadrata e **30°** su esagonale.
- I token piccoli (meno di una cella) si agganciano all'angolo, non al centro della cella. È una lamentela con **+235 voti** ([forum](https://app.roll20.net/forum/post/2309394/)). [Frolls+] Token piccoli centrati nella cella, o 4 sotto-posizioni.

### Regole per le diagonali
**Griglia quadrata:**
1. **D&D 5E/4E** (default): ogni passo diagonale vale 1 cella (5 ft).
2. **Pathfinder/3.5**: le diagonali si alternano 1 e 2 celle (5, 15, 20, 30 ft...), cioè 1.5 per diagonale arrotondato per difetto.
3. **Manhattan**: diagonale = 2 celle.
4. **Euclidea**: diagonale = √2 ≈ 1.414.

**Griglia esagonale:**
1. **Percorso esagonale**: +1 per ogni esagono attraversato sul percorso più breve.
2. **Euclidea**.

### Dati
Su `Page`: `grid_type ∈ {none, square, hex_h, hex_v}`, `diagonal_rule ∈ {dnd5e, pf35, manhattan, euclidean, hexpath}`, `cell_size_px`, `scale_number`, `scale_unit`.

---

## 6. Navigazione del canvas

- **Zoom**: menu nella toolbar con passi del 10%; slider +/- con percentuale (doppio clic sullo slider = 100%); **Alt/Ctrl/Cmd + rotella**; tasti **+ e -** (ignorati se un menu contestuale come i marker è aperto). Lo zoom è **per utente**.
- **Comportamento della rotella** configurabile per partita e come default dell'account:
  - "Rotella = pan": Alt/Ctrl+rotella zooma, Maiusc+rotella fa pan orizzontale.
  - "Rotella = zoom": Alt/Ctrl+rotella fa pan verticale, Alt+Maiusc+rotella fa pan orizzontale.
- **Pan**: modalità Pan della toolbar, oppure **trascinamento con il tasto destro** in qualunque momento, oppure barre di scorrimento.
- **Ping**: tenendo premuto il clic sinistro su un punto compaiono anelli radar animati **del colore dell'utente**, visibili a tutti sulla stessa pagina.
- **Pull ping** (solo GM): **Maiusc + tenere premuto** centra la vista di **tutti** i giocatori su quel punto. In Roll20 legacy funzionava solo sui layer mappa e oggetti.
- **Zoom view**: tasto **Z** con un oggetto selezionato apre un popup ingrandito dell'immagine. **Maiusc+Z** (GM) lo mostra a tutti i giocatori **sulla stessa pagina**.
- **Frecce**: spostano il token selezionato di una cella; **Alt+frecce** di pochi pixel.

### Casi limite
- Il pull ping deve funzionare anche per chi sta su un'altra pagina? In Roll20 no, vale solo per chi è sulla pagina. [Decisione Frolls] Solo stessa pagina.
- [Frolls+] Ping anche dei giocatori con un modificatore, ad esempio un ping che "chiama il GM".

---

## 7. Oggetti grafici e token

### 7.1 Creazione
- Un'immagine trascinata sul layer **oggetti** o **GM** diventa un **token**; sul layer mappa è un'immagine "di sfondo" senza funzioni da token.
- Fonti: Art Library (GM), file dal computer (upload e posizionamento), personaggio dal Journal (il suo token di default, per GM e per chi lo controlla), compendium (crea un PNG, vedi §18), carta da un mazzo, tabella casuale (token multi-faccia).
- **"Come disegno"** (Avanzate > Is Drawing): toglie le funzioni da token (niente barre, bolle, snap) ed è selezionabile insieme ai disegni con Alt.

### 7.2 Manipolazione (strumento Seleziona)
- **Selezione**: clic. **Selezione a rettangolo**: trascinare su un'area vuota. **Maiusc+clic** aggiunge o toglie dalla selezione. **Alt+rettangolo** seleziona solo i disegni, **Ctrl+rettangolo** solo i token. Si seleziona solo sul layer attivo. **Ctrl+A** seleziona tutto il layer.
- **Spostamento**: trascinare dall'interno (non dal bordo, che ridimensiona). Il gruppo selezionato si muove insieme.
- **Waypoint**: durante il trascinamento di un token, **Q** mostra un righello della distanza percorsa e ogni Q successivo aggiunge un waypoint. Al rilascio tutti vedono il percorso.
- **Ultimo movimento**: **X** con un token selezionato mostra il suo ultimo movimento con i waypoint, conservato **senza scadenza** (utile per il gioco via forum).
- **Ridimensionamento** (**solo GM**): maniglie agli angoli (proporzionale) e ai lati (un asse), dal centro, con snap alla griglia (Alt lo ignora). "Imposta dimensioni" accetta valori esatti in pixel o celle. **I giocatori non possono ridimensionare i propri token** ([wiki Player](https://wiki.roll20.net/Player)).
- **Rotazione**: maniglia sporgente in alto (il "fronte" del token). **E+rotella** ruota a passi di 45° o 30°, **Alt+E+rotella** di 1°.
- **Rifletti** orizzontale o verticale (Avanzate).
- **Raggruppa / Separa** (Avanzate): il gruppo si muove come un blocco; un clic su un singolo membro lo trascina da solo.
- **Ordine (z-order)** (solo GM): tasto destro, "In primo piano" o "In fondo".
- **Copia/Incolla/Elimina**: Ctrl+C, Ctrl+V, Canc o Backspace.
- **Annulla**: Ctrl+Z. È **un solo livello** e premendolo di nuovo si alterna tra fatto e annullato: lamentela forte ([forum](https://app.roll20.net/forum/post/3210982/please-review-the-undo-slash-redo-code), [forum](https://app.roll20.net/forum/post/5809236/problem-with-undoing)). I giocatori non avevano l'annulla ([forum](https://app.roll20.net/forum/post/8760735/player-undo-button-ctrl-plus-z)). [Frolls+] Annulla/ripeti a più livelli per utente, anche per i giocatori sui propri oggetti.
- **Blocco token** (GM, da marzo 2022): impedisce a giocatori **e GM** di spostarlo, finché non viene sbloccato.

### 7.3 Regole dello z-order (dal 2019)
- Di default l'ultimo token rilasciato sta sopra.
- Il GM riordina liberamente.
- **Per il giocatore che lo controlla**, un token "con vista" appare sempre sopra quelli che non controlla, anche se il GM l'ha messo sotto. Gli altri vedono l'ordine del GM.
- I token controllati **senza vista** (ad esempio i template incantesimo) non vengono portati in primo piano.
- Lamentele: ordine incoerente tra GM e giocatori ([forum](https://app.roll20.net/forum/post/8928459/)); i giocatori non possono riordinare i propri token ([forum](https://app.roll20.net/forum/post/7892438/)); richiesta di poter disattivare il "sempre sopra" ([forum](https://app.roll20.net/forum/post/11577293/)).
- Senza la visione (esclusa), [Decisione Frolls]: z-order unico e coerente per tutti; opzione per partita "token dei giocatori sempre sopra"; i giocatori possono riordinare i token che controllano rispetto ad altri token che controllano.

### 7.4 Menu radiale (token selezionato)
Visibile al selezionatore secondo i permessi:
1. **Tre bolle** di valore (verde, blu, rossa) per barra 1, 2 e 3. Clic per modificare: valore assoluto (`20`, anche testo `ABC`) oppure **relativo** (`+5`, `-10`). Colori configurabili dal GM.
2. **Nameplate** (se attivo).
3. **Modifica/Impostazioni** (solo GM; anche doppio clic sul token).
4. **Marker di stato** (menu a tendina).
5. **Pausa animazione** (token animati).

### 7.5 Impostazioni token (dialogo)
Schede: Dettagli, Note GM, (Luci e visione: escluse). Le modifiche si applicano in tempo reale.

**Dettagli**
- **Nome** e checkbox **Nameplate** (mostra il nome sotto il token). Permessi per il nome: *Vedono* (i giocatori vedono il nameplate) ed *Editabile* (chi controlla può modificarlo).
- **Rappresenta il personaggio**: menu di tutti i personaggi in ordine alfabetico, oppure "Nessuno/Generico".
- **Controllato da**: multiselezione di giocatori o "Tutti i giocatori". Se il token rappresenta un personaggio, il controllo **eredita** il "Controllato da" del personaggio.
- **Tooltip** (ottobre 2021): testo di massimo **150 caratteri** mostrato **sotto il token al passaggio del mouse**, con checkbox "Mostra". Spazi e a capo vengono rimossi (lamentela), le emoji sono supportate. È pensato anche per gli screen reader.
- **Barre 1-3**: ognuna ha **valore** e **max** (opzionale; se c'è, la barra visiva mostra il riempimento valore/max). Se il token rappresenta un personaggio, la barra può essere **collegata a un attributo**: la modifica dalla bolla, dal dialogo, dalla scheda o da uno script aggiorna **entrambi**. Permessi per barra: *Vedono* e *Editabile*, più visibilità dei numeri: **nessuno / solo chi controlla / tutti**.
- **4ª barra**: aggiunta di recente come impostazione "Numero massimo di bolle/barre". Le richieste di più barre esistevano da anni ([forum](https://app.roll20.net/forum/post/1285136/), [forum](https://app.roll20.net/forum/post/11729667/)).
- **Opzioni barre**: **posizione** (Sopra [default], Sovrapposta in alto, Sovrapposta in basso, Sotto) e **stile** (Standard o Compatto in alto/basso/sovrapposto). La posizione "sovrapposta in basso" collide con il nameplate: bug noto.
- **Aure 1-2**: cerchio o **quadrato** ("Square") semitrasparente che parte dal **centro del token**. Ha **raggio** in unità di scala misurato **dal bordo del token** (raggio 0 disegna l'aura sul bordo; per toglierla si **svuota** il campo, non si mette 0), **colore** e permessi *Vedono*/*Editabile*.
- **Tinta**: colore che si sovrappone all'immagine.
- **Note GM**: testo ricco privato del GM, con link al journal.

**Default di partita per i token**: valori e max delle barre, aure, tinta, nameplate e tutti i permessi vedono/editabile (vedi §23).

### 7.6 Marker di stato
- Set di default: puntini colorati, una **X rossa** (copre l'intero token, a differenza degli altri marker che sono piccoli) e oltre 40 icone. Più marker insieme.
- **Numero sul marker**: con il mouse sopra un marker nel menu si preme **0-9** e appare una cifra rossa; 0 la toglie.
- **Posizione** dei marker: sopra (default), sotto, sinistra, destra (impostazione GM).
- **Set personalizzati** (dal 2020): libreria account (consigliati 512×512, png/jpg/gif senza animazione); nomi con solo lettere, numeri e trattino (lo spazio diventa `_`). Si aggiungono alla partita dalla pagina Dettagli e si ordinano. Il set di default si può rimuovere, ma **non** i puntini colorati né la X. Rimuovere un set nasconde i marker sui token; riaggiungerlo li fa ricomparire. I giocatori devono ricaricare per vedere i nuovi set (lamentela).
- [Frolls+] Marker con durata in round collegata al turn tracker; condizioni 5e SRD precaricate.

### 7.7 Token multi-faccia (da tabella casuale)
- Da una tabella casuale con icone si crea un token che contiene tutte le immagini **nel momento della creazione**. Le modifiche successive alla tabella **non** si propagano: lamentela.
- Nasce come "disegno" (niente snap né barre) e va convertito a mano.
- Menu: **Multi-faccia > Scegli faccia** (slider) oppure **Faccia casuale** (i pesi della tabella **non** vengono usati).
- Può rappresentare un personaggio ed essere il suo token di default (forme selvatiche, varianti).
- [Frolls+] Facce collegate dinamicamente alla tabella.

### 7.8 Token di default e collegamento al personaggio
- Il personaggio ha un **token di default**: si seleziona un token sul tavolo e si preme "Usa token selezionato". Viene salvata una copia completa (barre, collegamenti, permessi, note).
- Trascinando il **nome** del personaggio dal Journal sul tavolo nasce una copia del token di default. Lo può fare il GM o chi "può modificare e controllare" il personaggio.
- **Solo il GM** può cambiare il token di default o l'avatar ([wiki Player](https://wiki.roll20.net/Player)). [Frolls+] Permetterlo anche al giocatore proprietario.
- **PG e PNG unici**: barre **collegate** agli attributi, così token e scheda restano sincronizzati.
- **Mostri generici**: barre **non collegate**. Ogni copia ha i suoi PF ma condivide la scheda per tiri e statistiche.
- **Maiusc+doppio clic** sul token apre la scheda collegata; dal 2023 c'è anche la voce "Apri scheda" nel menu contestuale.
- [Frolls+] Numerazione automatica delle copie ("Goblin 1, 2, 3", oggi serve lo script TokenNameNumber) e PF casuali dai dadi vita al posizionamento (oggi serve lo script MonsterHitDice).

### 7.9 Token Actions
Vedi §13.4.

### Dati token
```
Token(id, page_id, layer, x, y, width, height, rotation, flip_h, flip_v, z,
      image_asset_id, sides[] , current_side, is_drawing, locked,
      name, show_nameplate, name_perm{see,edit},
      represents_character_id, controlled_by[user_id|"all"],
      bars[1..4]{value, max, link_attr_id?, see, edit, numbers_visibility},
      bar_location, bar_style,
      auras[1..2]{radius, color, square, see, edit},
      tint_color, status_markers[{marker_id, number?}],
      tooltip{text<=150, show}, gm_notes_html,
      group_id, last_move{path[]}, created_at)
```

---

## 8. Strumenti di disegno

### Strumenti
- **Forme**: rettangolo; **Alt** per il cerchio/ellisse; **Maiusc** per lo snap alla griglia.
- **Mano libera**: si trascina come su una lavagna. Maiusc dà le linee dritte agganciate.
- **Poligono/Linea**: clic per ogni vertice. **Tasto destro o Esc** chiudono la forma; un vertice vicino al primo chiude il poligono; tasto destro dopo il primo segmento lascia una linea aperta. **Ctrl+Z** annulla segmento per segmento durante il disegno; Maiusc aggancia i vertici alla griglia.
- **Testo**: clic e si scrive. Font, dimensione e colore valgono per **tutto l'oggetto**, non per singoli caratteri ("è un'etichettatrice"). Doppio clic o tasto destro > Modifica per rientrare; Esc toglie il focus.
- **Barra secondaria**: colore del **tratto**, colore del **riempimento** (anche trasparente), **spessore** della linea.
- **Cancella disegni**: elimina **tutti i disegni del layer corrente**.
- **Raggruppa** disegni (Avanzate).

### Permessi
- **I giocatori possono sempre disegnare**, su qualunque pagina in cui si trovano, sul layer oggetti. Il GM non può impedirlo senza uno script (DryErase).
- I giocatori possono spostare ed eliminare i propri disegni; nel 2023 è sparita la loro possibilità di ridimensionarli ([forum](https://app.roll20.net/forum/post/11501167/)).
- [Frolls+] Permesso di partita "i giocatori possono disegnare" (sì/no/solo su pagine marcate) e "cancella i miei disegni".

### Dati
`Drawing(id, page_id, layer, kind: rect|ellipse|freehand|polygon|polyline|text, points[], stroke_color, stroke_width, fill_color, text, font_family, font_size, x, y, rotation, z, owner_id, group_id)`

### Casi limite
- Ctrl+F apre lo strumento mano libera **invece** della ricerca del browser: è una lamentela ([wiki Journal](https://wiki.roll20.net/Journal)). [Frolls+] Non rubare le scorciatoie del browser.
- Manca la gomma ([forum](https://app.roll20.net/forum/post/3756/eraser-tool)) e il contagocce ([forum](https://app.roll20.net/forum/post/1509/)). [Frolls+] Aggiungerli.

---

## 9. Misura e template ad area (AoE)

### 9.1 Righello legacy
- Clic e trascinamento misurano la distanza usando la scala e la regola diagonale della pagina.
- Modalità: **snap all'angolo** (misura in celle intere), **snap al centro** (celle intere), **libera** (distanza esatta).
- Visibilità: **"Mostra agli altri"** (tutti la vedono) oppure **"Nascondi agli altri"** (il GM la vede comunque).
- Durante la misura, **Q** o tasto destro aggiunge un waypoint; **Maiusc** la lascia visibile fino al tasto destro o a una nuova misura; **X** richiama l'ultima misura.

### 9.2 Strumento Misura (dal 2023, standard in Jumpgate)
- **Forme**: **Linea**, **Quadrato** (origine: centro, bordo o angolo), **Cerchio** (origine: centro o bordo), **Cono**, **Raggio/Beam** (linea con larghezza).
- **Angolo del cono**: "Larghezza = altezza" (**53,13°**, la regola 5e), preset rapidi o angolo personalizzato.
- **Snap**: regolabile.
- **Linger**: la misura resta sul tavolo.
- Ogni misura mostra **nome e colore** di chi misura.
- L'interfaccia indica se la misura sarà trasmessa agli altri o nascosta.
- Fonti: [Help Center](https://help.roll20.net/hc/en-us/articles/360039674913-Measure-Tool), [blog](https://blog.roll20.net/posts/new-measure-tool-shows-aoe-and-shapes/), [X/Roll20](https://x.com/roll20app/status/1887940210240930057).

### 9.3 Template persistenti
In Roll20 legacy si usavano token con aura o disegni come template. Non esiste un template AoE come oggetto persistente con evidenziazione delle celle colpite.
- [Frolls+] Oggetto **Template** persistente (cono, sfera, cubo, linea, cilindro) collegabile all'incantesimo, con **celle colpite evidenziate** secondo la regola 5e (cella colpita se coperta almeno a metà, o regola configurabile) ed elenco dei token colpiti. Era una richiesta storica ([forum](https://app.roll20.net/forum/post/8270654/advanced-rulers-cone-square-circles-beam)).

### Dati
`Measurement(user_id, page_id, shape, origin, points[], angle, width, snap_mode, visibility: all|gm, linger)`. Le misure temporanee sono solo realtime e non persistono; quelle con linger diventano oggetti.

---

## 10. Turn tracker (ordine di iniziativa)

### Comportamento
- **Solo il GM** lo apre e lo chiude. Aperto, **è visibile a tutti**; chiuso, si chiude per tutti.
- **Non è automatizzato** per scelta: serve a qualunque sistema.
- **Aggiungere turni**:
  - Tasto destro sul token > **Aggiungi turno** (anche più turni per lo stesso token), oppure **Ctrl+U** sui selezionati.
  - Tiro con flag **`&{tracker}`** con un token selezionato (anche dal pulsante Iniziativa della scheda). Se nessun token è selezionato appare l'avviso *"You wanted to send the result of this roll to the turn tracker, but no valid token was selected!"*. Con il token sbagliato selezionato, il valore va comunque su quel token.
  - **Voce personalizzata** (senza token): nome più eventuale **calcolo di round** (`+1` o `-1`) applicato ogni volta che la voce arriva in cima. Si usa come contatore di round o per buff a scadenza; funziona solo con più di una voce.
  - **Carte**: "Distribuisci carte alle voci del turn order" (Savage Worlds), oppure trascinare una carta sul campo del valore.
- **Valori**: clic sul numero e digitazione, poi Invio. Lo possono fare GM e giocatori (i giocatori sui propri). Si può trascinare il risultato di un tiro dalla chat sul campo valore. `&{tracker:+}` e `&{tracker:-}` sommano o sottraggono al valore attuale; se il token non è ancora nel tracker il tiro lo **aggiunge** ignorando il segno. Se il token ha già un turno, `&{tracker}` aggiorna **tutti** i suoi turni.
- **Avanzare**: freccia, il turno in cima va in fondo. **Indietro**: pulsante "back" aggiunto più tardi.
- **Riordino**: drag & drop; **ordina** numericamente (crescente o decrescente), alfabeticamente o per seme delle carte.
- **Rimuovere**: icona cestino al passaggio del mouse; **Svuota lista**.
- **Più pagine**: il tracker contiene token di qualunque pagina. Il GM vede tutto, **i giocatori vedono solo le voci della loro pagina**.
- **Token sul layer GM**: nome grigio nel tracker e voce **non mostrata ai giocatori**.
- **Riferimento in macro**: `@{tracker|Nome voce}` restituisce il valore.

### Lamentele principali
- **Nessun contatore di round** nativo: richiesto da oltre 10 anni ([forum](https://app.roll20.net/forum/post/494250/), [forum](https://app.roll20.net/forum/post/1242008/), [forum](https://app.roll20.net/forum/post/294139/)). Roll20 ha detto che "nel codice non esiste il concetto di round".
- Obbligo di **selezionare il token** prima di tirare l'iniziativa; vecchi tiri da ripulire a mano; controlli sparsi in un pannello separato; nessuna integrazione con PF e CA ([forum](https://app.roll20.net/forum/post/11481189/fixing-initiative-and-the-turn-tracker), +21).
- Mancano stato e durata per voce ([forum](https://app.roll20.net/forum/post/1170023/), [forum](https://app.roll20.net/forum/post/3478727/)).
- Manca l'iniziativa di gruppo (oggi serve lo script GroupInitiative).

### [Frolls+]
- Contatore di **round** e **turno attivo** evidenziato sul token, con centratura opzionale.
- L'iniziativa da scheda va al **token del personaggio sulla pagina corrente** anche senza selezione.
- "**Tira iniziativa per i selezionati/per tutti i PNG**" in un clic.
- Durate delle condizioni che scalano automaticamente.
- Spareggio 5e (bonus Destrezza).
- Chiedere se svuotare il tracker alla chiusura.
- Vista GM con CA, PF e percezione passiva.

### Dati
`TurnOrder(game_id, open: bool, round: int, entries[{id, token_id?, page_id?, custom_name?, value: string, formula?: "+1", hidden: bool}], current_index)`

---

## 11. Chat

### 11.1 Base
- Si scrive e si invia con **Invio**. **Maiusc+Invio** va a capo: ogni riga è interpretata **separatamente**, ma il blocco resta contiguo (non si mescola con i messaggi degli altri).
- **"Parla come"**: menu sotto l'input con sé stessi (nome visualizzato) oppure uno dei personaggi che si **controlla**. Il GM vede tutti i personaggi.
- **Avatar in chat** (impostazione personale): avatar dell'utente, o ritratto del personaggio se si parla come personaggio.
- **Timestamp**: **sempre salvati**, visualizzazione opzionale per utente (meno di 24 ore: solo l'ora; più vecchi: data e ora).
- **Freccia su** nell'input richiama l'ultimo comando o tiro della sessione, anche quello di un pulsante della scheda: è il modo per vedere la formula.
- **Bip in background**: suono per i nuovi messaggi quando non si è sulla scheda chat.
- **Popout** della chat con doppio clic sull'icona.
- **Il GM può nascondere messaggi** (da dicembre 2022).
- **Markdown supportato**: `*corsivo*`, `**grassetto**`, `***entrambi***`, codice con doppio backtick, `[testo](url)`. Un link che finisce in .png, .jpg, .jpeg o .gif viene mostrato come **immagine**. Niente titoli. Vale per messaggi, `/w`, `/desc`, `/em` e campi dei roll template.
- **Escape con backtick**: un messaggio che inizia con `` ` `` non viene interpretato (né tiri, né attributi, né macro) e va in chat letterale. Serve a condividere le macro.
- **Pulisci log** (impostazione personale): svuota solo la propria vista fino al ricaricamento.

### 11.2 Comandi

| Comando | Chi | Effetto |
|---|---|---|
| `/roll F` · `/r F` | tutti | tiro pubblico della formula F (§12) |
| `/gmroll F` · `/gr F` | tutti | tiro visibile **solo al GM e a chi tira** |
| `/w Nome testo` | tutti | sussurro a un giocatore o personaggio; nomi con spazi tra `"virgolette"`; **completamento con Tab**. Sussurrare a un **personaggio** lo manda a tutti quelli in "Controllato da" (trucco usato per le "lingue") |
| `/w gm testo` | tutti | sussurro a tutti i GM |
| `/em testo` · `/me testo` | tutti | emote come l'identità "parla come"; stile centrato, grassetto e corsivo, marrone |
| `/ooc testo` · `/o testo` | tutti | fuori personaggio: appare **sempre** come il giocatore, mai come il personaggio |
| `/desc testo` | GM | descrizione senza autore; stile centrato, grassetto e corsivo su grigio |
| `/as "Nome" testo` | GM | parla come un PNG qualsiasi senza personaggio nel journal |
| `/emas "Nome" testo` | GM | emote come un PNG qualsiasi |
| `/talktomyself [on/off]` | tutti | i propri messaggi successivi **non** arrivano a nessuno, né al GM né all'archivio. Il toggle va su una riga a parte; con il toggle attivo gli script API non partono |
| `/fx tipo-colore idSorgente [idBersaglio]` | GM (Pro) | effetto visivo (§20) |
| `#nomeMacro` | tutti | esegue una macro (§13) |
| `%{personaggio|abilità}` | tutti | esegue un'abilità |
| `&{template:nome} {{k=v}}...` | tutti | messaggio con roll template |
| `!comando` | tutti | comando API (Pro) |

### 11.3 Archivio chat
- La cronologia **persiste tra le sessioni**. In cima alla chat c'è "Vedi tutti i messaggi della partita", che apre l'archivio in un'altra finestra. "Mostra su una pagina" permette di salvare in HTML o PDF dal browser. Nell'archivio c'è un filtro "Nascondi sussurri".
- **Visibilità**: ognuno vede solo i sussurri e i tiri GM di cui era partecipante. Una vecchia nota del wiki dice che erano conservati solo i sussurri al GM.
- **Svuota archivio** (Creatore, Dettagli partita): permanente, serve digitare `CONFIRM`. Si usa anche quando la chat "si corrompe" e smette di funzionare: lamentela implicita sull'affidabilità.

### Lamentele e [Frolls+]
- **Tiri ciechi**: oggi non esiste un tiro che il giocatore fa senza vederne il risultato. È la richiesta più votata tra quelle sui dadi: **+410** ([forum](https://app.roll20.net/forum/post/4922089/)), più una simile a +39 ([forum](https://app.roll20.net/forum/post/11459035/)). Le soluzioni attuali sono hack CSS o script ([wiki Hidden Rolls](https://wiki.roll20.net/Hidden_Rolls)). [Frolls+] Comando **`/br`** (blind roll), il GM può forzarlo sui tiri della scheda, e il GM può chiedere un tiro cieco a un giocatore.
- Ricerca testuale nella chat e nell'archivio, esportazione in JSON o Markdown, caricamento paginato (archivi grandi lenti).
- Sussurro a più destinatari (oggi serve lo script DiscreteWhisper).
- [Decisione Frolls, già presa] Un messaggio che è **interamente** un'espressione di dadi valida (`d20`, `2d20kh1+5`) si tira senza `/roll`.

### Dati
`ChatMessage(id, game_id, sender_user_id, speaking_as{type:user|character|freeform, id?, name}, type: text|roll|emote|ooc|desc|whisper|gmroll|blind|template|system, recipients[]?, content_raw, content_rendered, rolls[] (risultati strutturati), template_name?, fields{}, hidden_by_gm, created_at)`

---

## 12. Motore dadi (specifica completa)

> Fonte principale: [Dice Reference](https://wiki.roll20.net/Dice_Reference) e [Order of Operations](https://wiki.roll20.net/Order_of_Operations). I tiri in Frolls sono **calcolati dal server** con un RNG crittografico e conservati in forma strutturata, così il log è verificabile.

### 12.1 Dove si tira
- `/roll F`, `/r F`, `/gmroll F`, `/gr F`.
- **Tiro inline** `[[F]]` dentro qualunque messaggio, emote, sussurro o campo di un template.
- Pulsanti della scheda, macro, abilità, token actions, GUI dei dadi.
- [Decisione Frolls] Un messaggio composto solo da una formula valida viene tirato automaticamente.

### 12.2 Testo, etichette ed escape
- Dopo la formula si può scrivere testo libero: `/roll 1d20+5 Per l'iniziativa`.
- Se il testo contiene numeri o operatori (`+ - * / % ( )`), va separato con `\`: `/roll 1d20+5 \ +5 Per l'iniziativa`.
- **Etichetta inline** `[testo]` subito dopo un termine: `2d10+5[Fuoco] + 3d6[Ghiaccio]`. Compare come **tooltip** sui dadi e nel dettaglio del tiro. Può contenere attributi: `@{selected|str}[str]`.

### 12.3 Tipi di dado
| Sintassi | Significato | Vincoli |
|---|---|---|
| `NdX` | N dadi da X facce. `dX` = `1dX` | N ≥ 0, X ≥ 1. Limite client Roll20: **≤ 999 dadi** e **≤ 9.999.999 facce**, oltre arrotonda in silenzio ([forum](https://app.roll20.net/forum/post/9164629/)) |
| `NdF` | dadi Fate/Fudge: facce −1, −1, 0, 0, +1, +1 | |
| `(espr)dX`, `Nd(espr)` | numero di dadi o facce calcolato; il numero di dadi è **arrotondato** come `round()` | |
| `NtX[nome]`, `1t[tabella]` | tiro su una **tabella casuale** (§14) | dentro un tiro inline viene mostrato **un solo** risultato qualunque sia N |

[Decisione Frolls] Errore esplicito, non arrotondamento silenzioso, oltre i limiti (proposta: 1000 dadi, 10^6 facce). `d%` come alias di `d100` (Roll20 non lo documenta).

### 12.4 Matematica
- Operatori: `+ - * /`, `%` (modulo; con a < 0 il risultato è negativo), `**` (potenza; radici con esponenti frazionari).
- Funzioni: `floor(x)`, `ceil(x)`, `round(x)` (≥ .5 verso +∞), `abs(x)`.
- Precedenza: `( )` > funzioni > `**` > `* / %` (da sinistra) > `+ -` (da sinistra).
- **Non ci sono** `min()` e `max()` ([forum](https://app.roll20.net/forum/post/1146425/)). Si aggira con i gruppi: `{a, b}kh1` = max. [Frolls+] Aggiungere `min`, `max` e operatori di confronto.
- Tiri solo matematici: `/roll 5+3`, `[[5+3]]`.

### 12.5 Compare Point (CP)
Molti modificatori confrontano ogni dado con un **CP**: un operatore opzionale tra `=`, `>`, `<` seguito da un numero.
- **Senza operatore vale `=`**.
- **`>` significa ≥** e **`<` significa ≤**: inclusivi, attenzione.
- Esempi: `=3`, `>2` (≥2), `<18` (≤18).

### 12.6 Modificatori sui dadi (B = dadi base, F = Fate)
| Modificatore | Sintassi | Semantica | Default CP |
|---|---|---|---|
| **Esplosione** | `!` · `!CP` | se il dado soddisfa il CP se ne tira **un altro** che si aggiunge come dado separato, ripetendo finché soddisfa | faccia massima |
| **Composta** | `!!` · `!!CP` | come l'esplosione, ma i tiri extra si **sommano nello stesso dado**: un dado può superare il massimo (Shadowrun, 7th Sea, L5R) | faccia massima. `5d6!!5`: compone sul 5, il 6 è un tiro normale |
| **Penetrante** | `!p` · `!pCP` | come l'esplosione, ma **ogni** tiro aggiuntivo ha **−1** (sempre e solo −1, anche dopo più penetrazioni; HackMaster) | faccia massima |
| **Ritira** | `r` · `rCP` (ripetibile: `r1r3r5`) | se il dado soddisfa il CP lo si **scarta e ritira**, finché non lo soddisfa più | `=1` (`8d6r` ritira gli 1) |
| **Ritira una volta** | `ro` · `roCP` | come `r`, ma una sola volta per dado, tenendo il nuovo risultato (es. Stile di combattimento Armi grandi 5e) | `=1` |
| **Tieni alti** | `khN` · `kN` | tieni gli N più alti; gli altri sono mostrati **in grigio** e non contano | `k` = `kh` |
| **Tieni bassi** | `klN` | tieni gli N più bassi | |
| **Scarta bassi** | `dlN` · `dN` | scarta gli N più bassi | `d` = `dl` |
| **Scarta alti** | `dhN` | scarta gli N più alti | |
| **Successi** | `CP` dopo i dadi: `3d6>3`, `10d6<4` | il risultato diventa il **numero di dadi** che soddisfano il CP (≥3, ≤4); i pari contano come successo | |
| **Fallimenti** | `fCP` (solo se c'è già un CP di successo) | ogni dado che soddisfa sottrae 1 dai successi: `3d6>3f1`, `10d6<4f>5` | |
| **Critico (solo visuale)** | `csCP`, `cfCP` (ripetibili: `cs20cs10`) | cambia **solo l'evidenziazione** del critico o del fallimento, **non** esplosioni o altro | cs = massimo, cf = 1 |
| **Coppie (match)** | `m[N][CP]` · `mt[N][CP]` | `m` evidenzia con una **barra colorata** (un colore diverso per ogni gruppo) i dadi uguali, senza cambiare il totale. `mt` restituisce il **numero di gruppi** di coppie. N = quanti dadi uguali servono per un gruppo (default 2); CP = valori ammessi (`5d6mt3>4`) | N = 2 |
| **Ordina** | `s` · `sa` · `sd` | ordina la visualizzazione crescente (default) o decrescente | `s` = `sa` |

**Ordine di applicazione dei modificatori su un gruppo di dadi:**
1. **Mentre i dadi "rotolano"**: esplosione, composta, penetrante, ritira (anche "una volta").
2. **A dadi fermi**: tieni/scarta, successi, fallimenti, ordinamento.

Esempio: per esplodere su ≥18 **e** mostrare il critico su ≥18 si scrive `1d20!>18cs>18`.

**Casi limite da coprire nei test:**
- `{5d6!!}>8`: le parentesi graffe servono a dire "compone sul 6, poi conta i successi ≥8". Senza graffe `5d6!!>8` significherebbe "compone su ≥8".
- `{3d6+1}<3`: per aggiungere un modificatore **a ogni dado** prima del confronto bisogna usare un gruppo.
- **Ritiro o esplosione infinita**: `1d1!`, `1d6r<6`, `1d6!>1`. Roll20 non documenta un tetto. [Decisione Frolls] Tetto di 100 esplosioni o ritiri per dado e avviso nell'output; rifiutare un CP che copre tutte le facce in `r`.
- `kh` con N maggiore dei dadi: tiene tutto. N = 0: tiene nulla (totale 0).
- I modificatori possono essere combinati, ad esempio `8d6!r1kh4sd`. [Decisione Frolls] Accettare qualunque ordine testuale e applicare l'ordine semantico qui sopra.

### 12.7 Tiri raggruppati `{ }`
- `{espr1, espr2, ...}` con modificatori di gruppo dopo la `}`.
- **Un solo sotto-tiro** (senza virgole): i modificatori di gruppo agiscono sui **singoli dadi** di tutto il gruppo, anche di tipi diversi.
  - `{4d6+3d8}k4`: dei 7 dadi tiene i 4 più alti.
  - `{3d20+5}>21`: somma 5 a **ogni** d20, poi conta quelli ≥21.
  - `{2d6!}>4`: esplode, poi conta i ≥4.
- **Più sotto-tiri** (separati da virgole): ognuno viene **sommato**, poi i modificatori agiscono sui **totali**.
  - `{4d6,3d8}kh1`: tiene il totale più alto (Savage Worlds: dado tratto più dado selvaggio).
  - `{4d6+2d8, 3d20+3, 5d10+1}d1`: scarta il totale più basso.
  - `{...}>40f<10`: conta i totali ≥40 e sottrae quelli ≤10.
- **Modificatori di gruppo**: `khN klN dhN dlN`, successi `CP`, fallimenti `fCP`.
- **Vincolo di tipo**: tutti i sotto-tiri devono essere dello stesso tipo, cioè tutti somme o tutti successi. Un numero da solo è un tipo speciale ("M roll"): `[[{1d6, 5}kh1]]` **fallisce**, mentre funzionano `{1d6, 5+0d0}kh1`, `{1d6, {5}}kh1` e `{[[1d6]], 5}kh1`. [Decisione Frolls] Far funzionare anche `{1d6, 5}kh1`, che è il modo naturale di scrivere `max(1d6, 5)`.
- I gruppi si possono annidare.

### 12.8 Tiri inline `[[ ]]`
- Si usano in qualunque messaggio: `/em mi colpisce per [[2d6+2]] danni`.
- Sono valutati **prima** del resto della riga, quindi si possono usare come variabili: `/roll [[2d6]]d5`.
- **Annidabili**: si valuta dal più interno: `[[ 3d6>[[1+3]] ]]`.
- **Visualizzazione**: solo il **totale** in un riquadro (giallo). **Al passaggio del mouse** si vede la formula con i dadi singoli e le etichette.
- **Evidenziazione**: bordo **verde** se c'è un critico, **rosso** se c'è un fallimento critico, **blu** se ci sono entrambi. Nel dettaglio i singoli dadi sono evidenziati in verde o rosso.
- Gli attributi auto-calcolati della scheda vanno racchiusi in `[[ ]]` per mostrare il valore e non la formula: lamentela, la scheda espone formule grezze.

### 12.9 Riuso dei tiri (comportamento emergente)
- `$[[n]]` è un riferimento al tiro inline n-esimo **della stessa riga** (indice da 0 in ordine di valutazione, dal più interno). Mostra il risultato senza ritirare.
- Non si può usare dentro un altro tiro inline senza romperlo; esiste però `$[[n.computed]]`.
- `%NEWLINE%` mantiene la stessa "riga" logica.
- È nato come bug sfruttato dalla community ([wiki Reusing Rolls](https://wiki.roll20.net/Reusing_Rolls)). [Frolls+] Variabili esplicite e documentate, ad esempio `[[1d20]]=>atk` e poi `$atk`, oltre alla compatibilità con `$[[n]]`.

### 12.10 Roll query `?{}`
- `?{Prompt}` mostra un input libero; `?{Prompt|default}` lo precompila.
- **Menu a tendina**: `?{Prompt|Op1|Op2|Op3}`, oppure con **etichetta e valore**: `?{Prompt|Etichetta 1,valore1|Etichetta 2,valore2}`.
- **Stessa domanda = una sola richiesta**: query con testo identico nello stesso comando chiedono una volta e riusano il valore. Si può riusare anche senza opzioni: `?{Deadly Aim}` dopo `?{Deadly Aim|Sì,1|No,0}`.
- Funzionano ovunque (tiri, macro, abilità, emote, sussurri).
- **Annidamento**: `|`, `,` e `}` dentro una query annidata vanno scritti come entità HTML (`&#124;`, `&#44;`, `&#125;`), con `&amp;` in più a ogni livello. Le chiamate `@{}`, `%{}` e `#` non vanno mai codificate. Le macro della scheda Collezioni **perdono le entità** quando vengono riaperte e salvate, e diventano rotte: lamentela storica, per questo la community salva le macro come abilità.
- [Frolls+] Parser con annidamento vero (parentesi bilanciate) e senza entità; un **dialogo unico** per tutte le query di un comando invece di un popup per volta; tipi di input (numero, sì/no).

### 12.11 Flag di tiro `&{...}`
- `&{tracker}`, `&{tracker:+}`, `&{tracker:-}` (§10).
- `&{noerror}`: sopprime gli errori, ad esempio un attributo inesistente.
- `&{template:nome}`: roll template (§13.6).

### 12.12 Ordine delle operazioni (fondamentale per la compatibilità delle macro)
1. Espansione delle **abilità** `%{car|abil}`.
2. Espansione delle **macro** `#nome`.
3. Risoluzione degli **attributi** `@{...}`.
4. Ripetizione dei passi 1-3 fino a **99 livelli** o finché non c'è più nulla da espandere.
5. **Roll query**, fino a 99 livelli. Dopo ogni query le entità HTML vengono decodificate **una volta**.
6. **Tiri inline**, dal più interno.
7. Tiro dei **dadi** della formula restante.
8. **Funzioni** matematiche.
9. Valutazione dell'**espressione** con la precedenza matematica.
10. Custom Roll Parsing (scheda).
11. Decodifica delle entità HTML (una volta).
12. Invio in chat (e agli script API).

Conseguenza: non si può costruire un nome di attributo con una query (le query vengono dopo gli attributi). È un limite noto. [Decisione Frolls] Mantenere questo ordine per compatibilità, ma documentarlo nell'editor.

### 12.13 Rendering dell'output
- `/roll`: i **dadi singoli** sono mostrati come forme del dado colorate con il **colore del giocatore**; scartati in grigio; critico e fallimento evidenziati; totale dopo il `=`.
- **Dadi avanzati** (impostazione): le icone dei dadi in chat si possono trascinare per riordinarle o sul tavolo.
- **GUI dei dadi**: tiro rapido fino a 5 dadi d4-d20 con un clic; opzioni GM roll, esplosivi, composti, penetranti; tiratore avanzato con tipo, numero e modificatore; **ultimi 10 tiri** da ripetere, compresi quelli fatti in chat.
- **Dadi 3D** (§20).

### 12.14 Grammatica di riferimento (per l'implementazione)
```
expr      := term (('+'|'-') term)*
term      := factor (('*'|'/'|'%') factor)*
factor    := unary ('**' factor)?
unary     := '-' unary | atom label?
atom      := number | dice | group | func '(' expr ')' | '(' expr ')' | inline | table
dice      := count? 'd' (sides | 'F' | '%') dmods*
count     := number | '(' expr ')'
sides     := number | '(' expr ')'
dmods     := explode | compound | penetrate | reroll | rerollonce
           | keep | drop | success | failure | crit | match | sort
explode   := '!' cp?        compound := '!!' cp?      penetrate := '!p' cp?
reroll    := 'r' cp?        rerollonce := 'ro' cp?
keep      := 'k' ('h'|'l')? number     drop := 'd' ('h'|'l')? number
success   := cp             failure := 'f' cp
crit      := ('cs'|'cf') cp match := ('m'|'mt') number? cp?
sort      := 's' ('a'|'d')?
cp        := ('='|'<'|'>')? number
group     := '{' expr (',' expr)* '}' gmods*
gmods     := keep | drop | success | failure
inline    := '[[' expr flags* ']]'
table     := number 't' '[' name ']'
label     := '[' text ']'
func      := 'floor'|'ceil'|'round'|'abs'  (+ Frolls: 'min'|'max')
```
Ambiguità da risolvere: `d` come "scarta" e `d` come "dado" (`2d6d1` = 2d6 scarta 1 basso); `>` come successo e `!>` come esplosione. La regola è l'aggancio al dado precedente.

### 12.15 Dati di un tiro
```
RollResult(id, expression_original, expression_expanded, total, type: sum|success|match,
  parts[{kind:dice|number|group|table, label?, sides, dice[{value, dropped, exploded_from?,
         rerolled[], crit:success|fail|null, match_group?}], subtotal}],
  seed_ref, created_at, roller_user_id, visibility)
```

---

## 13. Macro, abilità, riferimenti e template

### 13.1 Macro (Collezioni)
- Si creano nella scheda **Collezioni**: **nome** e **azione** (testo multilinea, una riga per comando).
- Opzioni:
  - **Visibile a**: giocatori con cui la macro è condivisa; il GM può renderla visibile a tutti.
  - **Mostra nella quick bar**: attivarla accende anche la barra.
  - **Mostra come token action**.
- Ogni giocatore può creare macro proprie; quelle del GM condivise appaiono agli altri.
- **Esecuzione**: `#nome` in chat, clic in Collezioni, clic nella quick bar o tra le token actions.
- **Variabile di coda**: `#d20` definita come `/roll 1d20+`, scrivendo `#d204` diventa `/roll 1d20+4`.
- **Annidamento**: `#altra` su una riga propria. In una query si scrive `,#macro ` con lo spazio dopo il nome.
- **Autocompletamento** nell'editor e in chat: `#` (macro), `@` (attributi dei personaggi controllati), `%` (abilità, solo in chat). Trova le corrispondenze per sottostringa e si naviga con frecce e Invio. Mostra solo ciò che si ha il permesso di vedere.
- **Maiusc+clic** su un pulsante macro apre l'editor.

### 13.2 Abilità (per personaggio)
- Si trovano nella scheda "Attributi e abilità" del personaggio: nome, azione e "Mostra come token action".
- `%{Personaggio|abilità}` oppure `%{selected|abilità}` / `%{target|...}`. **Serve sempre una parola chiave**, anche dentro il personaggio stesso: `%{abilità}` da solo non funziona (lamentela).
- I pulsanti della scheda si comportano come abilità (`%{Nome|nome_pulsante}`).
- **Maiusc+clic** apre l'editor dell'abilità.

### 13.3 Riferimenti agli attributi
| Sintassi | Significato |
|---|---|
| `@{attr}` | attributo del personaggio corrente (in abilità o scheda) |
| `@{Personaggio|attr}` | attributo di un personaggio per nome (**non** distingue maiuscole) |
| `@{Personaggio|attr|max}` | valore max |
| `@{selected|attr}` | dal token **selezionato**: se rappresenta un personaggio legge i suoi attributi |
| `@{selected|bar1}`, `bar1|max` | barre del token (anche non collegate) |
| `@{selected|token_name}`, `token_id`, `character_name`, `character_id` | identità |
| `@{target|attr}` | chiede di **cliccare un token bersaglio**, anche non controllato |
| `@{target|Nome|attr|max}` | bersagli multipli con nome (stesso nome = un solo prompt, anche su più righe) |
| `@{Personaggio|repeating_sezione_$0_campo}` | sezione ripetuta per **indice** (da 0) |
| `@{...|repeating_sezione_<rowid>_campo}` | sezione ripetuta per **ID di riga** (stabile) |
| `@{tracker|Nome}` | valore nel turn tracker |

Casi limite:
- Un attributo auto-calcolato restituisce la **formula** e va racchiuso in `[[ ]]`.
- Un attributo inesistente dà errore (`&{noerror}` lo sopprime).
- `selected` senza selezione dà errore.
- [Decisione Frolls] Ambiguità se due personaggi hanno lo stesso nome: si sceglie il primo per ID e si mostra un avviso.

### 13.4 Token Actions
- Barra in alto quando si seleziona un token. Contiene **tutte le macro** marcate come token action (su qualunque token) e le **abilità** marcate del personaggio rappresentato dal token.
- Ordinamento **alfabetico** di default (trucchi: prefissi numerici, simboli, spazi a larghezza zero), oppure "legacy" nell'ordine delle abilità (impostazione per utente).
- Le token actions definite **dentro il codice della scheda** non si possono togliere. [Frolls+] La scheda 5e propone token actions predefinite (attacchi, tiri salvezza, iniziativa) disattivabili per personaggio. Oggi serve lo script TokenActionMaker.

### 13.5 Macro quick bar
- Si attiva dalle impostazioni o attivando "nella barra" su una macro. Sta in basso, sotto gli avatar.
- **Drag** per riordinare, **trascinare fuori** per rimuovere (diventa rosso).
- Ci si possono trascinare i **pulsanti della scheda** (non funziona con le schede in popout).
- **Tasto destro**: **Rinomina** e **Colore** dello sfondo (il testo si adatta per contrasto), solo per l'utente locale.

### 13.6 Roll template
- Forma: `&{template:nome} {{campo=valore}} {{...}}`. I valori possono essere testo o tiri inline (macro e abilità dentro devono produrre tiri inline, non `/roll`). Si usano in messaggi normali e sussurri, **non** con `/roll`.
- **Sensibili agli spazi**: `{{ name=x}}` non funziona (lamentela).
- **Template `default`** (in ogni partita): `name` va nell'intestazione viola, ogni altro `{{chiave=valore}}` diventa una riga con chiave in grassetto e righe a colori alternati bianco e grigio, `=` allineato. I campi con chiave numerica (≥0) vengono ordinati **prima** degli altri, in ordine numerico. Le chiavi possono contenere tiri.
- I template specifici (5e: `simple`, `atk`, `dmg`, `atkdmg`, `npcatk`, `npcaction`, `spell`, `traits`, `desc`...) appartengono alla scheda e hanno logica condizionale (ad esempio `rollGreater()`, mostra/nascondi sezioni).

### 13.7 Pulsanti in chat (chat menu)
- `[Etichetta](~Personaggio|abilità)`, oppure `[Etichetta](~abilità)` dentro il personaggio: **pulsante abilità** cliccabile in chat.
- `[Etichetta](!comando)`: pulsante API.
- Servono a creare **menu in chat** in alternativa alle query annidate.
- Nel journal: link con URL che inizia con `` ` `` seguito dal codice macro (**pulsante comando del journal**). Non funziona se i personaggi sono in popout.

### Lamentele e [Frolls+]
- Le entità HTML e le query annidate sono la prima fonte di frustrazione ([wiki Macros](https://wiki.roll20.net/Macros)).
- Le macro non si trasferiscono tra partite (il Transmogrifier non le copia; trucco della "scheda macro").
- [Frolls+] **Libreria macro dell'account** riusabile tra le partite; editor con evidenziazione della sintassi e anteprima; condivisione delle macro con un link.

### Dati
`Macro(id, game_id, owner_user_id, name, action, visible_to[], in_bar, token_action)`, `UserBarEntry(user_id, game_id, ref_type: macro|ability|sheet_button, ref_id, label_override, color, order)`, `Ability(id, character_id, name, action, token_action, order)`

---

## 14. Tabelle casuali (Rollable Tables)

- Si trovano in **Collezioni**, solo il GM le crea. "Aggiungi" crea "new-table" con 0 elementi.
- **Tabella**: nome (senza spazi in pratica, perché si usa in `1t[nome]`) e "**Mostra ai giocatori**" (necessario perché i giocatori possano usarla nelle macro).
- **Elemento**: nome o testo (mostrato in chat quando esce), **icona** opzionale (l'immagine compare in chat) e **peso**. Il peso si esprime come numero di occorrenze oppure in percentuale; in percentuale si scrive senza `%` e il totale deve fare 100.
- **Uso**:
  - Pulsante **Tira** in Collezioni: il risultato va in chat e tra gli ultimi 10 tiri della GUI.
  - `/roll 1t[nome]`, `/roll 3t[nome]` (più estrazioni).
  - Inline `[[1t[nome]]]`, con un solo risultato visibile anche se N > 1 e gli altri al passaggio del mouse.
- Si usano per dadi personalizzati (elementi numerici) e per tabelle di critici o bottino.
- **Token** dalla tabella: vedi §7.7.
- Lamentele: non c'è tabella annidata (un risultato che tira su un'altra tabella, oggi serve RecursiveTable); i tiri inline dentro il testo di un elemento non vengono valutati; non c'è import/export (serve TableExport).
- [Frolls+] Tabelle annidate, tiri inline nei risultati, import CSV, intervalli in stile d100 ("01-15 = goblin").

### Dati
`RollTable(id, game_id, name, show_to_players)`, `RollTableItem(id, table_id, name, weight, icon_asset_id, order)`

---

## 15. Mazzi di carte

### Cosa fa
Ogni partita nasce con un **mazzo standard da 54 carte** (52 più 2 jolly). Solo il GM crea mazzi.

### Comportamento
- **Mostra/Nascondi** il mazzo da Collezioni: il mazzo compare sul lato destro del tavolo, con barra di scorrimento se sono tanti.
- **Pescare**: clic sulla carta che sporge dietro il mazzo. La carta pescata appare scoperta **sopra il mazzo**, visibile a chi vede il mazzo.
- **Giocare sul tavolo**: trascinare la carta scoperta, oppure quella coperta da dietro il mazzo (senza rivelarla). Diventa un token. **Maiusc** durante il trascinamento la gioca dal lato opposto al default. Tasto destro sulla carta: **Gira**.
- **Distribuire**: trascinare una carta sul nome di un giocatore nell'area giocatori, oppure **Distribuisci** dal menu (quante carte, a chi, "Tutti i giocatori") o "Distribuisci alle voci del turn order". Sopra l'avatar del giocatore appare l'icona del mazzo con il numero di carte.
- **Mano**: il giocatore clicca l'icona e vede le carte; le riordina; vista unica o per mazzo; trascinarne una sul tavolo la gioca. **Prendi carta**: tasto destro su una carta del tavolo.
- **Rubare**: si apre la mano di un altro giocatore (di default si vedono solo i dorsi) e si sceglie una carta; il derubato deve **confermare**.
- **Scambiare**: trascinare una carta dalla propria mano sul nome di un altro giocatore apre un dialogo di scambio a due; entrambi aggiungono o tolgono carte e confermano.
- **Richiama**: dialogo con i conteggi in mano, sul tavolo, non giocate e totali; pulsanti per richiamare ogni gruppo; "Mescola al richiamo"; "Richiama tutto".
- **Mescola**: con conferma; rimette dentro prima la pila degli scarti.
- **Scarti**: raccoglie le carte giocate e poi eliminate dal tavolo, e quelle pescate ma mai giocate.

### Impostazioni del mazzo
- Nome.
- **Mostra il mazzo ai giocatori?**
- **I giocatori possono pescare?**
- **Carte infinite?** (non finiscono mai). Se il mazzo finisce durante la distribuzione appare l'errore *"Ran out of cards..."* e serve mescolare.
- **Nelle mani altrui** (per GM e per giocatori): vedi **numero di carte** e/o **fronte delle carte**. Default: solo il numero.
- **Pila degli scarti**: come si pesca da lì (solo la carta in cima o in fondo, oppure scegliendo tra tutte coperte o scoperte).
- **Carte giocate**: scoperte o coperte di default.
- **Dimensione delle carte sul tavolo** (vuoto = automatica).
- **Tooltip** per carta, attivabile per mazzo.
- **Dorso** comune a tutte le carte.
- **Carte**: nome, immagine, elimina; "**Aggiungi multiple**" per il caricamento in blocco (dal 2020). Fronti e dorso dovrebbero avere le stesse dimensioni.
- La dimensione dei mazzi a schermo si regola con uno slider del GM.

### Lamentele
- Mancano pile o mazzi sul tavolo ([forum](https://app.roll20.net/forum/permalink/2793233/)).
- Il "guarda le carte coperte che ho giocato" richiede uno script.
- Le carte selezionate non vanno in primo piano ([forum](https://app.roll20.net/forum/post/2344077/)).

### Dati
`Deck(id, game_id, name, back_asset_id, show_to_players, players_can_draw, infinite, hand_visibility{gm:{count,face}, players:{count,face}}, discard_draw_mode, play_face_down, card_size, tooltips_enabled)`, `Card(id, deck_id, name, asset_id, tooltip)`, `CardInstance(card_id, location: deck|discard|hand|table, owner_user_id?, token_id?, order)`

---

## 16. Journal

### 16.1 Generale
- È l'archivio centrale di **Personaggi** e **Handout**, organizzati in **cartelle**.
- **Solo il GM** crea personaggi e handout (pulsante + Aggiungi, oppure tasto destro su una cartella). Un personaggio nasce con un nome casuale, un handout con il nome "Mysterious Note".
- **Ricerca** e **tag** in cima.
- **Archivio** in fondo, che compare quando c'è almeno un elemento archiviato. Gli elementi archiviati **si caricano comunque** e non migliorano le prestazioni.
- **Riordino**: maniglia ≡ a sinistra del nome, trascinare sotto la cartella e poi a destra per entrare.
- **Finestre**: doppio clic sulla barra del titolo riduce la finestra a una barra trascinabile; si possono avere più finestre aperte, in popout o con zoom del contenuto.
- **Link tra voci**: `[Nome voce]` tra parentesi quadre nel testo diventa un **link** al salvataggio (viola verso handout o personaggi, blu verso compendium e URL). Rispetta i permessi: chi non ha accesso non può aprirla.
- **Link al compendium**: l'URL completo della pagina del compendium (senza `?` e `#`) si apre nel compendium interno.
- **Mostra ai giocatori** (GM): apre la voce sullo schermo dei giocatori. Se non hanno il permesso chiede se darlo a tutti, e "Mostra a tutti" aggiunge "Tutti i giocatori" ai permessi. Dal 2023 c'è una notifica quando qualcosa viene mostrato.
- **Trascinare un handout sull'avatar di un giocatore**: gli dà il permesso di vederlo e glielo apre subito.
- **Journal esterno** (Plus/Pro): pagina web fuori dal VTT con personaggi (solo Bio) e handout, aggiornata in tempo reale. Il trucco per cercare con Ctrl+F è usare lì il browser, perché nel VTT Ctrl+F è rubato.

### 16.2 Permessi (identici per personaggi e handout)
| Campo | Effetto |
|---|---|
| **Nei journal dei giocatori** | chi è elencato (o "Tutti") **vede** la voce. Per un personaggio vede solo nome, avatar e Bio: **non** la scheda né gli attributi |
| **Può essere modificato e controllato da** (personaggi) / **Può essere modificato da** (handout) | per un personaggio: lo può scegliere in "parla come", modifica nome e Bio, **vede e modifica la scheda e gli attributi**, controlla i token che lo rappresentano. Per un handout: lo vede e lo modifica |
| **Note GM** | sempre e solo GM |

Per far giocare un PG il GM deve aggiungere il giocatore **in entrambi** i campi: è una lamentela, due passaggi per un caso comune.

### 16.3 Cartelle
- Sottocartelle limitate a pochi livelli (circa 4), "per lo spazio nella sidebar": lamentela.
- **Visibilità**: un giocatore vede una cartella solo se contiene almeno un elemento a lui visibile. Vede però il **nome della cartella** che contiene un handout condiviso, per esempio "Oggetti maledetti", e questo può fare spoiler.
- Menu: aggiungi sottocartella, personaggio o handout; ordina A-Z; rinomina; elimina (gli elementi tornano alla radice, con conferma).

### 16.4 Personaggio
- Finestra con schede **Bio e info**, **Scheda personaggio** (se c'è un template) e **Attributi e abilità**.
- **Modifica** (solo GM):
  - Nome.
  - **Avatar** (drag da computer o Art Library).
  - **Token di default**.
  - Nei journal dei giocatori / Modificabile e controllabile da.
  - Tag.
  - Bio e Note GM in testo ricco, con tabelle e incolla da PDF o Word.
  - Duplica ("Copy of ..."), Archivia, Elimina (con conferma, irreversibile).
- **Attributi**: nome, valore attuale, max opzionale. Chi controlla il personaggio li aggiunge e modifica. Con una scheda attiva gli attributi la rispecchiano, tranne le sezioni ripetute, e modificarli a mano può rompere la scheda.
- **Abilità**: vedi §13.2. Si riordinano trascinandole.

### 16.5 Handout
- Contenuto: nome, **immagine** (con lente d'ingrandimento e schermo intero se è grande), **Descrizione e note** (testo ricco visibile a chi vede, modificabile da chi modifica), **Note GM**, tag, duplica, archivia, elimina.
- Incollare contenuto formattato conserva lo stile.

### Lamentele e [Frolls+]
- Le prestazioni crollano con centinaia di personaggi complessi ([wiki Optimizing](https://wiki.roll20.net/Optimizing_Roll20_Performance), [forum](https://app.roll20.net/forum/post/7085783/character-sheets-very-slow-to-open), [forum](https://app.roll20.net/forum/post/12443273/high-level-character-sheets-cause-intense-lag-and-crash)). [Frolls+] Caricamento lazy delle schede e degli attributi solo all'apertura; indice leggero per il journal.
- [Frolls+] Un solo pulsante "**Assegna a giocatore**", che imposta vede più controlla.
- [Frolls+] Ricerca full-text nel contenuto degli handout (oggi serve lo script Search).
- [Frolls+] Cartelle senza limiti di profondità e nomi delle cartelle non visibili ai giocatori, se scelto.
- [Frolls+] I giocatori possono creare i propri personaggi (impostazione GM). Oggi non possono senza un'opzione o uno script ([wiki Player](https://wiki.roll20.net/Player)).

### Dati
`Folder(id, game_id, parent_id, name, order)`, `Character(id, game_id, folder_id, name, avatar_asset_id, bio_html, gm_notes_html, tags[], in_journals[], controlled_by[], default_token_json, sheet_type: pc|npc, archived, is_party_member)`, `Attribute(id, character_id, name, current, max)` (indice su `character_id+name` minuscolo), `Handout(id, game_id, folder_id, name, image_asset_id, notes_html, gm_notes_html, tags[], in_journals[], editable_by[], archived)`

---

## 17. Scheda personaggio 5e (riferimento: "D&D 5E by Roll20", ex 5th Edition OGL)

> Frolls implementa una scheda **compatibile 5e** con contenuti **solo SRD 5.1/5.2** (CC-BY-4.0) e nomi propri, senza marchi WotC. Qui sotto c'è il comportamento della scheda Roll20, da replicare nelle funzioni e non nell'aspetto.

### 17.1 Principi
- Si salva automaticamente a ogni modifica.
- I campi **calcolati** non sono modificabili.
- Le **etichette tirabili** diventano rosse al passaggio del mouse; il clic tira con un roll template.
- I pulsanti sono **trascinabili** nella macro bar.
- **Sezioni ripetute** (attacchi, inventario, incantesimi, tratti, competenze, risorse): pulsante + aggiungi; il **lucchetto** alterna "aggiungi" e "riordina/elimina" (≡ trascina, cestino elimina **senza conferma**: lamentela).
- Pagine della scheda PG: **Principale**, **Bio**, **Incantesimi**, **Impostazioni** (ingranaggio). Interruttore **PNG** per la scheda mostro.

### 17.2 Pagina principale
- **Intestazione**: classe (12 classi più una personalizzata) e livello, fino a 4 classi in multiclasse; background, razza o specie, allineamento, PE. Il nome è sincronizzato con il nome del journal.
- **Caratteristiche** (FOR, DES, COS, INT, SAG, CAR): punteggio e **modificatore = floor((punteggio−10)/2)** (attributi `strength`, `strength_mod`...). I bonus razziali vanno nelle impostazioni.
- **Ispirazione** (toggle).
- **Bonus di competenza**: calcolato dal livello totale. In alternativa "dado di competenza" o personalizzato.
- **Tiri salvezza**: checkbox di competenza, preimpostate dalla classe principale; modificatore globale opzionale (es. `1d4[Bless]`).
- **Abilità (skill)**: 18, con caratteristica tra parentesi, competenza, **Maestria**, **Factotum** (metà competenza), bonus fissi; modificatore globale delle abilità (es. `1d4[Guidance]`).
- **CA**: automatica (10 + DES + armatura equipaggiata), personalizzata (fino a 2 attributi) o manuale; modificatori di CA globali in una sezione ripetuta attivabile. Più armature equipaggiate fanno comparire un **avviso rosso**.
- **Iniziativa**: calcolata da DES più un bonus; stile normale, vantaggio o svantaggio; **spareggio DES** opzionale come decimale (es. 2.14). Il clic con il token selezionato va al tracker.
- **Velocità**.
- **PF**: attuali, max e **temporanei**. Il danno scala prima i temporanei.
- **Dadi vita**: tipo dalla classe, numero dal livello, disponibili; il clic chiede quanti tirarne per tipo.
- **Tiri salvezza contro la morte**: tiro più checkbox successi e fallimenti, con modificatore.
- **Indebolimento** (opzionale): mostra gli effetti ma **non li applica**.
- **Attacchi e incantesimi** (ripetuta): nome, caratteristica (FOR, DES, incantatore o nessuna), competente, bonus, bonus magico, gittata, **danno 1** e **danno 2** (formula, caratteristica, tipo), **tiro salvezza** (caratteristica, CD, effetto "metà danni"), descrizione, **range di critico**. Modificatori globali di attacco e danno.
- **Tratti, ideali, legami e difetti**: campi bloccabili (gli a capo vengono rimossi: lamentela).
- **Risorse di classe e altre** (ripetibili): valore, max e nome; collegabili a un oggetto ("usa come risorsa": la quantità è sincronizzata). Le munizioni prese dal compendium si collegano da sole.
- **Strumenti e abilità personalizzate**: competenza, maestria o factotum; caratteristica fissa o **chiesta con una query**.
- **Altre competenze e lingue**: testo semplice o elenco tipizzato (Lingua, Arma, Armatura, Altro).
- **Equipaggiamento**: "Semplice" (testo) o "Compatibile compendium" (elenco). Ogni oggetto ha quantità, nome, peso, equipaggiato, usa come risorsa, proprietà e **MODS**. MODS è una stringa `Stat: n` separata da virgole (es. `Strength: 21`, `AC +1`, `Animal Handling +3`) e modifica le statistiche **solo se l'oggetto è equipaggiato**; la statistica modificata diventa **blu con asterisco** e il valore base si vede al passaggio del mouse. Monete: MR, MA, ME, MO, MP. **Ingombro**: peso totale e stati ENCUMBERED, HEAVILY ENCUMBERED, IMMOBILE (variante opzionale).
- **Privilegi e tratti** (ripetuta): nome, fonte, descrizione.

### 17.3 Pagina incantesimi
- Caratteristica da incantatore (automatica dalla classe), **CD = 8 + competenza + mod** e **bonus di attacco = competenza + mod**, entrambi calcolati.
- Livelli da 0 (trucchetti) a 9: **slot totali** (dal livello da incantatore, con multiclasse e modificatori manuali) e slot rimasti.
- Incantesimo (ripetuto): nome, scuola, rituale, tempo di lancio, gittata, bersaglio, componenti V/S/M e materiali, concentrazione, durata, output "Scheda" o "Attacco" (in quel caso aggiunge una voce agli Attacchi), tipo di attacco, danno, tiro salvezza, **ai livelli superiori** (dado per livello di slot), descrizione e classe.
- Icone R, C, V, S, M attivabili.

### 17.4 Impostazioni della scheda
Dadi vita, modificatore di trasporto, livello da incantatore manuale, modificatore della CD, Fortuna halfling (ritira gli 1, cioè `ro1`), multiclasse, classe personalizzata, slot extra, modificatori alle caratteristiche, iniziativa, CA, salvezze e TS contro la morte, percezione passiva. Opzioni generali:
- **Vantaggio**: "Tira sempre 2d20" (default Roll20: si usa quello di sinistra se non c'è vantaggio), "Interruttore" (pulsanti Vantaggio/Normale/Svantaggio in cima alla scheda), "Chiedi" (query), "Mai".
- **Sussurra i tiri al GM**: mai, interruttore, chiedi, sempre.
- **Danni automatici**: se no, il danno è nascosto e si mostra cliccando il nome dell'attacco in chat.
- **Dado base** (default 1d20).
- **Nome del personaggio nei template**.
- **Calcoli automatici al livello**.
- **Tracciamento munizioni** (con lo script companion).
- Mostra indebolimento.
- I default della scheda si impostano nella partita; "Applica impostazioni di default" li estende alle schede già esistenti.

### 17.5 Scheda PNG (mostro)
- **Opzioni PNG** (nascondibili): nome, taglia, tipo, allineamento, CA e descrizione della CA, PF e formula, velocità, caratteristiche, salvezze e abilità (**appaiono nel blocco solo se valorizzate**; 0 per mostrarle comunque), vulnerabilità, resistenze, immunità, immunità alle condizioni, sensi, lingue, **GS** (i **PE si calcolano** dal GS), "incantatore PNG" (aggiunge la lista incantesimi), "ha reazioni", "azioni leggendarie" (numero).
- **Blocco statistiche** con tutto cliccabile: Tratti, Azioni, Azioni bonus, Reazioni, Azioni leggendarie, Incantesimi. L'azione può essere un attacco (tiro, danno 1 e 2, critico) oppure testo.
- Opzioni proprie: sussurra al GM (consigliato per i PNG), danni automatici, nome del PNG nei tiri (default disattivo, così non si rivela il mostro), spareggio dell'iniziativa.

### 17.6 Roll template della scheda
- **simple**: un tiro o un tiro doppio per vantaggio/svantaggio, con nome della caratteristica.
- **atk/dmg/atkdmg**: attacco in alto, info al centro, danno in basso, critico con danno extra.
- **spell**: scheda dell'incantesimo in chat.
- **npcatk/npcaction**: azioni dei PNG.
- **traits** e **desc**.
- Con "tira sempre il vantaggio" i due d20 sono affiancati e si evidenzia quello scelto (con l'interruttore attivo).

### 17.7 Charactermancer
Procedura guidata di creazione e salita di livello basata sul compendium. Non funziona in popout.

### Lamentele e [Frolls+]
- Prestazioni: centinaia di attributi per scheda e lag con le schede di alto livello ([forum](https://app.roll20.net/forum/post/12443273/)). [Frolls+] Attributi in JSONB per personaggio, calcoli derivati lato client e validati lato server.
- Niente formattazione nei campi di testo; gli a capo vengono rimossi.
- Eliminare una voce di una sezione ripetuta avviene **senza conferma** e **senza annulla**. [Frolls+] Annulla e cestino.
- L'indebolimento non applica le penalità. [Frolls+] Condizioni 5e che applicano davvero vantaggio e svantaggio dove possibile.
- [Frolls+] Pulsante "**applica danno/cura**" dal template in chat ai token selezionati, con resistenze. Oggi serve uno script (ApplyDamage, ChatSetAttr).
- [Frolls+] Riposo breve e lungo in un clic (ripristino di PF, dadi vita, slot e risorse).

---

## 18. Compendium

- Raccolta di **regole indicizzate** come un mini-wiki: regole, classi, razze, mostri, incantesimi, oggetti. Si consulta **fuori** e **dentro** il VTT (scheda della sidebar, visibile a GM e giocatori). Le voci si aprono in finestre separate.
- **Elenchi** (incantesimi, mostri) con un blocco di dati espandibile per voce, filtri, ricerca e icona della fonte (libro).
- **Trascinamento**:
  - **Voce non-mostro sul tavolo**: crea un **handout** con testo e immagini (è anche il modo di condividere contenuto acquistato).
  - **Mostro sul tavolo**: crea un **personaggio PNG completo** con la scheda compilata e un **token collegato** (se disponibile) posizionato sul punto.
  - **Mostro su una scheda aperta**: la converte in PNG e **aggiunge** (non sostituisce) i dati.
  - **Oggetto o incantesimo sulla scheda**: appare "ACCEPTING DROP FROM COMPENDIUM" e il rilascio compila la sezione giusta; le armi creano anche un attacco, gli oggetti con MODS si applicano, le munizioni diventano risorse.
- **Impostazioni**: compendium dato dal template di scheda o scelto a mano; **condivisione** dei compendi acquistati con i giocatori della partita; selezione delle espansioni attive.
- **Lamentela più votata in assoluto tra quelle viste: "Compendium personalizzato" a +1732** ([forum](https://app.roll20.net/forum/post/2940484/)). Oggi non si può creare né modificare il compendium.
- [Frolls+] **Compendium SRD 5.1/5.2 integrato** più **compendium personalizzato** di partita o di account (homebrew di mostri, oggetti e incantesimi con la stessa struttura dati), importabile ed esportabile in JSON.

### Dati
`CompendiumEntry(id, source: srd|homebrew, owner_id?, kind: monster|spell|item|rule|class|race|condition, name, data_json, text_md, image_asset_id?)`

---

## 19. Art Library e asset

- **Solo GM** (i giocatori non hanno Art Library; lamentela: non possono caricare il proprio token o avatar).
- **Ricerca**: Mia libreria, Acquisti, set Pro, asset gratuiti, premium e "dal web" (vecchio indice). Più parole sono in **AND**, `OR` esplicito, `-parola` esclude. Filtri per tipo: token, mappe, tile, texture, ritratti. Miniature piccole o grandi.
- **Upload**: trascinare un file sul tavolo (carica e posiziona) oppure dal dialogo **fino a 10 file per volta**. **Limite per file o lotto: 5 MB** gratis, **10 MB** per gli abbonati (vicino al limite fallisce). Tipi: **jpg, png, gif, gif animate, mp4, webm, PDF** (si sceglie la pagina da convertire). Il `.jpeg` in passato non era accettato: bug. Gli upload animati sono lenti o vanno in timeout ([wiki](https://wiki.roll20.net/Art_Library)).
- **Quota di spazio**: 100 MB gratis, 3 GB Plus, 8 GB Pro, 50 GB Elite. Superarla blocca gli upload ma non cancella nulla. I contenuti del marketplace non contano.
- **Recent Uploads**: tutte le immagini in ordine cronologico. Le cartelle sono **riferimenti**. Eliminare da Recent Uploads cancella **definitivamente**, anche dalle partite che la usano.
- **Cartelle** (fino a 3 livelli) con menu: sottocartella, ordina A-Z, rinomina, elimina (le immagini tornano in Recent).
- **Vista cartella**: selezione multipla, sposta, elimina, **tag** (il nome del file diventa un tag; spazio o Invio confermano il tag).
- **Copia in libreria**: crea riferimenti agli asset premium senza consumare quota.
- [Frolls+] Upload più grandi; conversione automatica in WebP o AVIF; deduplicazione per hash; miniature generate; avviso "questa immagine è usata in N pagine" prima di eliminarla; **i giocatori possono caricare avatar e token dei propri personaggi** entro una quota.

### Dati
`Asset(id, owner_user_id, storage_key, mime, bytes, width, height, sha256, animated, created_at)`, `AssetFolder(id, owner_user_id, parent_id, name)`, `AssetTag(asset_id, tag)`

---

## 20. Effetti visivi e dadi 3D (priorità bassa)

- **FX** (GM, Pro): `/fx tipo-colore idSorgente [idBersaglio]`. Tipi: beam, bomb, breath, bubbling, burn, burst, explode, glow, missile, nova, splatter. Colori: acid, blood, charm, death, fire, frost, holy, magic, slime, smoke, water. Beam e breath sono **direzionali** (sorgente e bersaglio); gli altri sono ad area (solo sorgente). Esistono effetti personalizzati e uno strumento FX per piazzarli col mouse.
- **Dadi 3D**: simulazione fisica sopra il tavolo (WebGL). Con "Dice Agency" si trascina per lanciare; altrimenti il lancio è automatico. Colore del giocatore. Il d100 usa due d10 (00-90 e 0-9). Si vedono i dadi degli altri se anche loro hanno l'opzione attiva. **In caso di discrepanza fa fede la chat**: i template possono tirare dadi poi nascosti. Si disattiva per utente.
- [Decisione Frolls] I dadi 3D devono essere **solo animazione** di un risultato già calcolato dal server, così non ci sono discrepanze.

---

## 21. Map Pins (2025)

- Il GM trascina un **handout** (o un'intestazione o ancora dentro un handout) sulla mappa e crea un **pin** che riprende immagine, titolo, testo e note GM.
- Strumento "Posiziona pin" e tasto destro sulla mappa creano anche pin non collegati.
- Opzione "**blockquote come testo per i giocatori**": la prima citazione va nel tooltip dei giocatori, il resto nelle note GM.
- I pin si **ridimensionano**.
- Fonti: [Help Center](https://help.roll20.net/hc/en-us/articles/36271267343639-Map-Pins-Early-Access), [blog](https://blog.roll20.net/posts/map-pins-open-beta/).

### Dati
`Pin(id, page_id, x, y, scale, handout_id?, anchor?, title, player_text, gm_text, icon, visible_to_players)`

---

## 22. API / Mod scripts (Pro), solo sintesi

- Script **JavaScript** eseguiti in una sandbox lato server della partita. Si installano da un repository della community ([roll20-api-scripts](https://github.com/Roll20/roll20-api-scripts)) o si scrivono a mano. Riservati al Creatore Pro.
- **Reattivi** (eventi `chat:message`, `change:graphic`, `add:...`) e **proattivi** (timer). Possono leggere e modificare tutti gli oggetti, creare handout, mandare messaggi in chat e gestire comandi `!comando`.
- Gli script più usati mostrano cosa manca nel prodotto base, quindi sono la **lista dei desideri per Frolls**:
  - **TokenMod**: modifica i token da chat.
  - **ChatSetAttr**: modifica gli attributi da chat.
  - **GroupInitiative**: iniziativa di gruppo.
  - **TurnMarker**: indicatore del turno.
  - **CombatMaster / RoundMaster**: condizioni con durata.
  - **ApplyDamage**.
  - **TokenNameNumber**.
  - **MonsterHitDice**.
  - **Search**: ricerca negli handout.
  - **DiscreteWhisper**.
  - **Blind roll**.
  - **TableExport / RecursiveTable**.
  - **Teleport**.
  - **MarchingOrder**.
  - **5e Companion**: munizioni, slot, dadi vita automatici.
- [Decisione Frolls] Nessun sistema di script nella prima fase: le funzioni sopra diventano **funzioni native**. In futuro, un sistema di plugin con permessi.

---

## 23. Impostazioni

### 23.1 Impostazioni partita (pagina web, Creatore)
- Accesso pubblico (journal e archivio visibili a chi visita).
- Sfondo della pagina della partita.
- **Consenti ai giocatori di importare personaggi** (dal Character Vault).
- **Default delle pagine**: tutte le impostazioni di pagina tranne play-on-load, archivia ed elimina.
- **Default dei token**: valori delle barre, aure, tinta, nameplate e permessi vedi/modifica per nome, barre e aure.
- Compendium: sistema, condivisione, espansioni.
- **Template di scheda** e **default della scheda** (§17.4).
- "**Applica impostazioni di default**" (in partita, GM) applica i default di pagine, token e schede a **tutto il contenuto esistente**, con barra di avanzamento, interrompibile con Esc e **irreversibile**.
- Le modifiche alla pagina delle impostazioni richiedono di **ricaricare** la partita già aperta: lamentela. [Frolls+] Impostazioni live, dentro il VTT.

### 23.2 Impostazioni personali (sidebar, per utente e per partita)
Nome visualizzato; scorciatoie avanzate; popout automatici per personaggi e handout; bip della chat; dadi avanzati; dadi 3D e lancio automatico; avatar in chat; timestamp; token actions in ordine alfabetico; rotella zoom o pan; pulisci log; esci; rientra come giocatore.

**Solo GM**: colori delle barre, posizione dei marker, dimensione dei mazzi, applica default.

### 23.3 Colore del giocatore
Si sceglie con il riquadro accanto al proprio nome nell'area giocatori. Si usa per ping, dadi, misure e cornice dell'avatar.

---

## 24. Altre funzioni

- **Character Vault**: archivio personale dell'account. **Importa** un personaggio da una partita (servono i permessi di modifica) come **snapshot** che non si aggiorna; per aggiornarlo si elimina e si reimporta. **Esporta** in un'altra partita: richiede che il GM lo consenta e Vault completo (abbonamento o modulo); dal luglio 2023 i free possono esportare fino a 3 personaggi per partita. Funziona anche tra partite di creatori diversi. Salva avatar, token, scheda e statistiche.
- **Transmogrifier** (Pro): copia pagine (con token), personaggi, handout, mazzi e tabelle tra **partite proprie** con drag & drop tra due elenchi. Copia, non sposta. Avvisa in caso di sovrascrittura (stesso ID originale). **Non copia giocatori né macro**, quindi i "Controllato da" vanno rifatti. Si usa per la "campagna libreria" che alleggerisce le partite.
- **Scorciatoie da tastiera di default**:
  - Layer: Ctrl+M/O/K, Ctrl+Maiusc+M/O/K.
  - Modifica: Ctrl+C/V/Z/A, Canc.
  - Strumenti: Ctrl+S seleziona, Ctrl+F mano libera, Ctrl+G testo, Ctrl+U aggiungi turno.
  - Misura e movimento: Q, Maiusc, X; Alt per ignorare lo snap; frecce; E+rotella; tasto destro+trascina per il pan; Z e Maiusc+Z.
  - Selezione: Alt+rettangolo (disegni).
  - Personaggi e macro: Maiusc+doppio clic sul token, Maiusc+clic su macro.
  - GM: Ctrl+T rientra come giocatore.
- **Scorciatoie avanzate** (opzionali): sequenze di tasti singoli (es. `F R` per le forme, `C C` per il focus sulla chat), mostra/nascondi sidebar, focus sulla ricerca del journal.
- **Journal esterno, archivio chat e forum della partita**: vedi sopra.
- **Moduli e addon del marketplace**: avventure pronte installate in una partita, con patch che aggiornano solo gli elementi cambiati. Fuori scope per ora; tenere a mente il formato di import ed export della partita.
- **Import UVTT** (2026): mappa con muri, porte e luci da file Universal VTT. Utile per l'import di mappe anche senza luci: si importa solo l'immagine e la griglia.
- **App mobile**: Roll20 ha app iPad e Android limitate. [Frolls+] Interfaccia responsive.

---

## 25. Lamentele trasversali (sintesi per le priorità)

| Problema | Fonte | Risposta di Frolls |
|---|---|---|
| Interfaccia datata e curva di apprendimento ripida | [gmcrafttavern](https://gmcrafttavern.com/foundry-vs-roll20-owlbear-2026/), [StoryRoll](https://storyroll.app/blog/best-online-dnd-platforms) | UI moderna, separata tra GM e giocatore, scorciatoie coerenti |
| Prestazioni: FPS bassi con molti token o asset grandi, schede lente, partite gonfie | [gmcrafttavern](https://gmcrafttavern.com/foundry-vs-roll20-owlbear-2026/), [wiki Optimizing](https://wiki.roll20.net/Optimizing_Roll20_Performance), [forum](https://app.roll20.net/forum/post/4192520/big-campaign-and-slow-performance) | PixiJS, sync a delta, caricamento lazy di pagine e schede |
| Funzioni base dietro abbonamento (luci, API, rollback, quota) | [Subscription](https://wiki.roll20.net/Subscription), [Elite](https://app.roll20.net/forum/post/12542863/) | Nessun paywall sulle funzioni di gioco |
| Annulla a un solo livello | [forum](https://app.roll20.net/forum/post/3210982/) | Annulla/ripeti a più livelli per utente |
| Nessun tiro cieco | [forum +410](https://app.roll20.net/forum/post/4922089/) | `/br` nativo |
| Nessun compendium personalizzato | [forum +1732](https://app.roll20.net/forum/post/2940484/) | Compendium homebrew |
| Turn tracker senza round né automazioni | [forum](https://app.roll20.net/forum/post/11481189/) | Round, condizioni, iniziativa di gruppo |
| Macro fragili (entità HTML, query annidate) | [wiki Macros](https://wiki.roll20.net/Macros) | Parser robusto, editor con anteprima |
| Token piccoli non centrati | [forum +235](https://app.roll20.net/forum/post/2309394/) | Snap al centro |
| Giocatori senza upload, senza ridimensionamento, senza z-order | [wiki Player](https://wiki.roll20.net/Player) | Permessi granulari decisi dal GM |
| Ctrl+F rubato al browser | [wiki Journal](https://wiki.roll20.net/Journal) | Ricerca interna, nessun furto di scorciatoie |
| Supporto clienti e moderazione criticati, violazione del 2018 | [octobergeek](https://octobergeek.wordpress.com/2018/09/30/why-im-staying-with-roll20-for-now/), [HIBP](https://haveibeenpwned.com/Breach/Roll20) | Sicurezza by design, export completo dei dati |
| Owlbear: setup in 30 secondi, nessun account per i giocatori, adatto al mobile | [gmcrafttavern](https://gmcrafttavern.com/foundry-vs-roll20-owlbear-2026/) | Link di invito che porta subito al tavolo; ingresso ospite valutabile |
| Foundry: automazione e moduli | [scriptoriumgm](https://www.scriptoriumgm.com/blog/best-virtual-tabletop-vtt-systems) | Automazioni 5e native, plugin in futuro |

---

## 26. Ordine di implementazione consigliato (vertical slice)

Ogni slice è **end-to-end**: modello Postgres, API o messaggi WebSocket, UI Svelte o Pixi e test. L'ordine tiene conto delle decisioni utente: auth per ultima, una sola partita persistente fino ad allora, dadi in chat senza comando.

1. **Persistenza e stato condiviso**: Postgres (pagine, token, eventi), caricamento di uno snapshot al join, delta sync, annulla/ripeti per utente (base del §7.2). *Uscita*: token persistenti dopo il riavvio.
2. **Canvas base**: una pagina con dimensioni, colore di sfondo, **griglia quadrata ed esagonale**, scala e unità; zoom, pan, frecce; **ping e pull ping**; upload di una **immagine mappa** (storage S3 o MinIO, o locale in dev) sul layer mappa.
3. **Token v1**: creazione da upload, spostamento con snap e Alt, ridimensionamento (GM), rotazione, rifletti, selezione multipla e a rettangolo, gruppo, z-order, copia/incolla/elimina, blocco, **layer mappa, oggetti e GM** con le regole di visibilità, waypoint e ultimo movimento.
4. **Motore dadi completo (server)** più **chat**: grammatica §12.14, tutti i modificatori, gruppi, inline, etichette, `/r /gr /w /em /ooc /desc /as /emas /talktomyself`, tiro automatico delle espressioni, `/br`, rendering dei dadi e del dettaglio, archivio persistente con paginazione. Test di proprietà sul parser.
5. **Token v2**: dialogo impostazioni, **barre 1-4** (valore, max, permessi, posizione e stile), bolle con valori relativi, **aure**, **marker** con numeri (set SRD delle condizioni), nameplate, tooltip, tinta, note GM, controllato da.
6. **Journal v1**: cartelle, **personaggi** (bio, note GM, avatar, attributi, abilità), **handout**, permessi vede/modifica più "assegna a giocatore", mostra ai giocatori, link `[Nome]`, archivio, ricerca. **Token di default**, drag dal journal, **barre collegate agli attributi**, "parla come".
7. **Macro e riferimenti**: `@{}` (selected, target, max, repeating, tracker), `%{}`, `#`, roll query con dialogo unico, ordine delle operazioni §12.12, `&{noerror}`, **roll template default**, pulsanti in chat, macro di Collezioni, **quick bar**, **token actions**.
8. **Turn tracker**: aggiungi turno, `&{tracker[:+|:-]}`, voci personalizzate con formula, avanti e indietro, ordinamento, visibilità per pagina e layer GM, **round**, turno evidenziato, iniziativa di gruppo.
9. **Pagine multiple**: page toolbar, cartelle, duplica, archivia, elimina con vincoli, **Player Ribbon**, **split party**, Define/Place Party, impostazioni pagina complete con le regole diagonali, copia di token tra pagine.
10. **Misura e AoE**: righello con snap e visibilità, waypoint, linea, quadrato, cerchio, cono (53,13°), raggio; template persistenti con celle e token colpiti.
11. **Disegno**: forme, mano libera, poligono, testo, colori e spessori, gomma, cancella layer, permesso "i giocatori disegnano".
12. **Scheda 5e PG** (SRD): calcoli automatici, tiri con template simple, atk e spell, vantaggio, sussurro, sezioni ripetute con annulla, inventario con MODS, incantesimi e slot, risorse, riposi; poi la **scheda PNG** con blocco statistiche cliccabile.
13. **Compendium SRD** con drag & drop (mostro sul tavolo diventa PNG più token; oggetto o incantesimo sulla scheda; voce diventa handout), poi il **compendium homebrew**.
14. **Tabelle casuali** (`1t[...]`, inline, pesi, annidate) e **token multi-faccia**.
15. **Mazzi di carte**: mazzo standard, pesca, gioca, mano, distribuisci, ruba, scambia, scarti, carte nel tracker.
16. **Art Library completa**: cartelle, tag, quota, ricerca, upload in blocco, PDF in immagine, animazioni, upload dei giocatori.
17. **Rifiniture di gioco**: map pins, zoom view (Z, Maiusc+Z), FX, dadi 3D solo come animazione, impostazioni personali e di partita live, scorciatoie avanzate, applica default.
18. **Account e partite (ultimo, come deciso)**: registrazione, OAuth (Google e Discord), più partite, ruoli Creatore, GM e Giocatore, **link di invito** rigenerato all'espulsione, promozione e retrocessione, dettagli della partita, copia della partita, export ed import completo della partita (JSON più asset), Character Vault.
19. **Futuro**: sistema di plugin (al posto delle API), marketplace, LFG, forum della partita, import UVTT. Poi le funzioni rimandate qui sotto.

---

## 27. Rimandati (fuori scope per ora)

- **Voce e video**: eliminati, non vanno sviluppati.
- **Audio / Jukebox** (playlist, play-on-load delle pagine, volume).
- **Fog of war** (base e avanzata).
- **Luci dinamiche** (muri, porte, finestre, luci, oscurità, layer luci).
- **Visione e linea di vista** (sight, scurovisione, Ctrl+L, limitazione del movimento).

---

## 28. Fonti

**Wiki Roll20 (community; lette tramite Wayback Machine)**
- [Dice Reference](https://wiki.roll20.net/Dice_Reference) · [Order of Operations](https://wiki.roll20.net/Order_of_Operations) · [Inline Rolls](https://wiki.roll20.net/Inline_Rolls) · [Roll Query](https://wiki.roll20.net/Roll_Query) · [Reusing Rolls](https://wiki.roll20.net/Reusing_Rolls) · [Hidden Rolls](https://wiki.roll20.net/Hidden_Rolls) · [Roll Templates](https://wiki.roll20.net/Roll_Templates) · [Default Roll Template](https://wiki.roll20.net/Default_Roll_Template) · [Dice Rolling GUI](https://wiki.roll20.net/Dice_Rolling_GUI) · [3D Dice](https://wiki.roll20.net/3D_Dice)
- [Text Chat](https://wiki.roll20.net/Text_Chat) · [Chat Archive](https://wiki.roll20.net/Chat_Archive) · [Chat Menus](https://wiki.roll20.net/Chat_Menus)
- [Macros](https://wiki.roll20.net/Macros) · [Token Actions](https://wiki.roll20.net/Token_Actions) · [Collections](https://wiki.roll20.net/Collections)
- [Token Features](https://wiki.roll20.net/Token_Features) · [Manipulating Tokens](https://wiki.roll20.net/Manipulating_Tokens) · [Token Markers](https://wiki.roll20.net/Token_Markers) · [Token Tooltip](https://wiki.roll20.net/Token_Tooltip) · [Token Lock](https://wiki.roll20.net/Token_Lock) · [Token Z-Ordering](https://wiki.roll20.net/Token_Z-Ordering) · [Multi-Sided Token](https://wiki.roll20.net/Multi-Sided_Token) · [Linking Tokens to Journals](https://wiki.roll20.net/Linking_Tokens_to_Journals) · [Waypoint](https://wiki.roll20.net/Waypoint)
- [Page Settings](https://wiki.roll20.net/Page_Settings) · [Page Toolbar](https://wiki.roll20.net/Page_Toolbar) · [Layers](https://wiki.roll20.net/Layers) · [Foreground Layer](https://wiki.roll20.net/Foreground_Layer) · [Ruler](https://wiki.roll20.net/Ruler) · [Zoom Tool](https://wiki.roll20.net/Zoom_Tool) · [Ping](https://wiki.roll20.net/Ping) · [Tabletop](https://wiki.roll20.net/Tabletop) · [Select Tool](https://wiki.roll20.net/Select_Tool) · [Drawing Tools](https://wiki.roll20.net/Drawing_Tools) · [Toolbox](https://wiki.roll20.net/Toolbox) · [Toolbar & Layers Redesign](https://wiki.roll20.net/Toolbar_%26_Layers_Redesign) · [Keyboard Shortcuts](https://wiki.roll20.net/Keyboard_Shortcuts) · [Advanced Shortcuts](https://wiki.roll20.net/Advanced_Shortcuts)
- [Turn Tracker](https://wiki.roll20.net/Turn_Tracker) · [Card Decks](https://wiki.roll20.net/Card_Decks) · [Rollable Table](https://wiki.roll20.net/Rollable_Table)
- [Journal](https://wiki.roll20.net/Journal) · [Handouts](https://wiki.roll20.net/Handouts) · [Character Sheet](https://wiki.roll20.net/Character_Sheet) · [D&D 5E by Roll20](https://wiki.roll20.net/D%26D_5E_by_Roll20) · [Compendium](https://wiki.roll20.net/Compendium) · [Art Library](https://wiki.roll20.net/Art_Library) · [Archiving](https://wiki.roll20.net/Archiving)
- [Game Details / Game Management](https://wiki.roll20.net/Game_Management) · [Game Settings](https://wiki.roll20.net/Game_Settings) · [My Settings](https://wiki.roll20.net/My_Settings) · [Player](https://wiki.roll20.net/Player) · [Gamemaster](https://wiki.roll20.net/Gamemaster) · [Character Vault](https://wiki.roll20.net/Character_Vault) · [Transmogrifier](https://wiki.roll20.net/Transmogrifier) · [Fx Tool](https://wiki.roll20.net/Fx_Tool) · [API Introduction](https://wiki.roll20.net/API:Introduction) · [Optimizing Roll20 Performance](https://wiki.roll20.net/Optimizing_Roll20_Performance) · [Subscription](https://wiki.roll20.net/Subscription)

**Help Center e blog Roll20**
- [Measure Tool](https://help.roll20.net/hc/en-us/articles/360039674913-Measure-Tool) · [Turn Tracker](https://help.roll20.net/hc/en-us/articles/360039178634-Turn-Tracker) · [Token Features](https://help.roll20.net/hc/en-us/articles/360039674573-Token-Features) · [Map Pins](https://help.roll20.net/hc/en-us/articles/36271267343639-Map-Pins-Early-Access) · [2025 Change Log](https://help.roll20.net/hc/en-us/articles/38597501957015-2025-Change-Log)
- [New Measure Tool Shows AoE and Shapes](https://blog.roll20.net/posts/new-measure-tool-shows-aoe-and-shapes/) · [Jumpgate Officially Launches](https://blog.roll20.net/posts/the-future-of-tabletop-gaming-jumpgate-officially-launches/) · [Map Pins open beta](https://blog.roll20.net/posts/map-pins-open-beta/) · [Define and Place Party](https://blog.roll20.net/posts/define-and-place-party/)

**Forum Roll20**
- Suggerimenti: [Custom Compendium +1732](https://app.roll20.net/forum/post/2940484/) · [GM rolls nascosti al giocatore +410](https://app.roll20.net/forum/post/4922089/) · [Secret rolls](https://app.roll20.net/forum/post/11459035/) · [Token piccoli centrati +235](https://app.roll20.net/forum/post/2309394/) · [Transmogrifier cartelle +583](https://app.roll20.net/forum/post/3234668/) · [Fixing Initiative and the Turn Tracker](https://app.roll20.net/forum/post/11481189/fixing-initiative-and-the-turn-tracker) · [Contatore di round](https://app.roll20.net/forum/post/494250/) · [Turn Tracker Enhancements](https://app.roll20.net/forum/post/1170023/) · [Più barre](https://app.roll20.net/forum/post/1285136/) · [4ª barra](https://app.roll20.net/forum/post/11729667/) · [Undo per giocatori](https://app.roll20.net/forum/post/8760735/player-undo-button-ctrl-plus-z) · [Undo/Redo](https://app.roll20.net/forum/post/3210982/please-review-the-undo-slash-redo-code) · [Gomma](https://app.roll20.net/forum/post/3756/eraser-tool) · [Mazzi avanzati](https://app.roll20.net/forum/permalink/2793233/) · [Righelli avanzati](https://app.roll20.net/forum/post/8270654/advanced-rulers-cone-square-circles-beam)
- Bug e tecnica: [Z-order non sincronizzato](https://app.roll20.net/forum/post/8928459/) · [Token sempre sopra](https://app.roll20.net/forum/post/11577293/) · [Token bar redesign](https://app.roll20.net/forum/post/7396014/token-bar-redesign-bug-thread) · [Schede lente](https://app.roll20.net/forum/post/7085783/character-sheets-very-slow-to-open) · [Schede di alto livello e crash](https://app.roll20.net/forum/post/12443273/high-level-character-sheets-cause-intense-lag-and-crash) · [Grande campagna lenta](https://app.roll20.net/forum/post/4192520/big-campaign-and-slow-performance) · [Limiti dei dadi](https://app.roll20.net/forum/post/9164629/) · [Niente min/max](https://app.roll20.net/forum/post/1146425/) · [Ridimensionamento disegni giocatori](https://app.roll20.net/forum/post/11501167/) · [Release Notes 23 maggio 2025](https://app.roll20.net/forum/post/12372218/release-notes-may-23rd-2025) · [Party Tools](https://app.roll20.net/forum/post/12465889/gm-time-save-alert-party-tools-are-here) · [Elite](https://app.roll20.net/forum/post/12542863/introducing-roll20-elite-5x-storage-4x-sharing-and-more)

**Repository pubblici**
- [Roll20/roll20-character-sheets](https://github.com/Roll20/roll20-character-sheets) · [Roll20/roll20-api-scripts](https://github.com/Roll20/roll20-api-scripts) (citati solo come riferimento all'ecosistema; non è stato letto codice)

**Recensioni, confronti e notizie**
- [GM Craft Tavern: Foundry vs Roll20 vs Owlbear 2026](https://gmcrafttavern.com/foundry-vs-roll20-owlbear-2026/) · [StoryRoll: Best Online D&D Platforms 2026](https://storyroll.app/blog/best-online-dnd-platforms) · [Scriptorium GM: VTT compared](https://www.scriptoriumgm.com/blog/best-virtual-tabletop-vtt-systems) · [Black Lantern Forge](https://blacklanternforge.com/blogs/news/roll20-vs-foundry-vtt-vs-owlbear-rodeo-which-virtual-tabletop-is-right-for-your-campaign) · [Dice Outpost](https://www.diceoutpost.com/guides/best-vtt-for-beginners/) · [Bell of Lost Souls: Party Tools](https://www.belloflostsouls.net/2025/08/roll20-unleashes-powerful-new-party-tools-after-recent-jumpgate-upgrades.html) · [GamingTrend: Map Pins](https://gamingtrend.com/news/roll20-unveils-new-map-pins-feature/) · [Have I Been Pwned: Roll20](https://haveibeenpwned.com/Breach/Roll20) · [October Geek](https://octobergeek.wordpress.com/2018/09/30/why-im-staying-with-roll20-for-now/) · [Wikipedia: Roll20](https://en.wikipedia.org/wiki/Roll20)

**Limiti della ricerca**: Reddit (r/Roll20, r/DnD) blocca l'accesso automatico, quindi le lamentele vengono dal forum ufficiale, dal wiki e dalle recensioni. L'Help Center e il wiki rispondono 403 alle richieste dirette, quindi le pagine del wiki sono state lette da copie d'archivio, che possono essere indietro di qualche mese sulle novità Jumpgate.
