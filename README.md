# Shorts Factory

Banda de productie pentru shorts animate in stil Roblox: idee -> script -> voce -> mix audio ->
fisa de job pentru animator -> (animatorul animeaza) -> asamblare finala cu subtitrari -> verificari.

## 1. Instalare (o singura data)

1. Instaleaza **Python 3.11+** si **ffmpeg 6+** (Windows: `winget install Gyan.FFmpeg`; Mac: `brew install ffmpeg`; Linux: `apt install ffmpeg`).
2. In folderul proiectului:
   ```
   python -m venv .venv
   .venv\Scripts\activate        (Windows)   |   source .venv/bin/activate   (Mac/Linux)
   pip install -r requirements.txt
   ```
3. Testeaza ca totul merge, fara nicio cheie API:
   ```
   python run.py selftest
   ```
   Trebuie sa scrie `SELFTEST TRECUT`. Rezultatul de test e in `projects/...-mock/`.
4. Copiaza `.env.example` ca `.env` si pune cheile: `ANTHROPIC_API_KEY` (platform.claude.com) si `ELEVENLABS_API_KEY` (elevenlabs.io -> Developers -> API keys).
5. Alege vocea: `python run.py voices`, copiaza `voice_id` in `config.yaml`.
6. Genereaza efectele sonore: `python run.py sfx-pack`. Pune muzica in `assets/music/<stare>/`.
7. Editeaza `config.yaml`: numele canalului si **biblioteca** (decorurile si personajele pe care le ai cu adevarat).

## 2. Fluxul zilnic

| Pas | Comanda | Ce primesti |
| --- | --- | --- |
| Idei | `python run.py ideas --n 15` | `projects/ideas_*.json`, lista punctata in terminal |
| Script | `python run.py new --ideas projects/ideas_X.json --pick 3 --script-only` | `projects/<slug>/script.md` de citit |
| (optional) editezi | modifici `script.json` cu mana | - |
| Pre-productie | `python run.py prep <slug>` | `master.wav`, `animatic.mp4`, `job_card.md`, `shots.csv` |
| Trimiti animatorului | cele 4 fisiere de mai sus | - |
| Primesti animatia | o salvezi ca `projects/<slug>/render.mp4` | - |
| Final | `python run.py final <slug>` | `final.mp4`, `qa_report.json`, `upload.txt` |

Fara `--script-only`, comanda `new` face direct si pre-productia.
Poti porni si de la o premisa scrisa de tine: `python run.py new --premise "A boy discovers ..."`.

## 3. Ce face fiecare fisier din proiect

- `script.json` / `script.md`: scriptul final (naratiune pe beats + cadru pentru fiecare beat + titlu/descriere).
- `script_v0.json`, `critic_1.json`: prima varianta si critica (ca sa vezi ce s-a schimbat).
- `voice.*`, `alignment.json`, `words.json`: vocea si momentul exact al fiecarui cuvant.
- `master.wav`: voce + muzica + efecte, normalizat la -14 LUFS (acelasi nivel masurat la canalul de referinta).
- `captions.json` / `captions.ass`: subtitrarile (2-5 cuvinte, cuvantul-cheie in rosu).
- `animatic.mp4`: video de referinta cu fiecare cadru descris pe ecran, pe audio-ul final.
- `job_card.md`, `shots.csv`: fisa de job pentru animator.
- `final.mp4`: video-ul de urcat. `qa_report.json`: verificarile. `upload.txt`: titlu, descriere, comentariu fixat.

## 4. Reglaje utile (config.yaml)

- Ritmul vocii: `voice.settings.speed` (max 1.2) si `voice.tempo` (accelerare suplimentara). Tinta: ~3.5 cuvinte/s; `prep` afiseaza valoarea obtinuta.
- Lungimea povestii: `story.min_words` / `max_words`.
- Subtitrari: `captions.*` (font, marime, pozitie, culori).
- Zoom pe cuvintele-cheie: `video.punch_in`.
- Calitatea scriptului: `llm.model` (`claude-opus-5-5` pentru calitate maxima) si `llm.critic_rounds`.

## 5. Probleme frecvente

- `Lipseste ANTHROPIC_API_KEY`: nu ai creat `.env` sau cheia e gresita.
- `Nu gasesc 'ffmpeg'`: ffmpeg nu e instalat sau nu e in PATH.
- Scriptul are erori la validare: deschide `script.json`, corecteaza ce scrie in terminal, ruleaza `prep` din nou.
- Animatia livrata are alta rezolutie/fps: se adapteaza automat; QA te avertizeaza daca e prea scurta.
