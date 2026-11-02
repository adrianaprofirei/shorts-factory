# Animatia fara animatori: cercetare si plan (1 noiembrie 2026)

Decizie: animatia o facem noi, ca sa avem tot ciclul in pipeline. Inlocuieste pasul "animatorul livreaza render.mp4".

## 1. Pe scurt
- Recomandare: **imagini-cheie AI + image-to-video AI, cadru cu cadru**, pornind de la `shots.json` pe care
  pipeline-ul il produce deja. Cost estimat **~$5-17 / video** (fata de $55-110 la animator), cateva zeci de minute.
- Asa se fac si povestile virale cu fructe: imagini de scena (Nano Banana) animate cu Veo 3.1 Fast sau Kling,
  montate apoi in CapCut. Nimeni nu le animeaza de mana.
- Varianta de rezerva, fara risc de AI-video: **Blender automatizat din Python** (personaje cubice, fete-decal).
  Gratis la rulare, dar cateva saptamani de constructie si "actorie" mai saraca.
- Inainte de orice decizie: **pilot de o saptamana** pe scriptul existent ("sorry"), cu 2 furnizori, comparat pe
  consistenta personajelor, cost si timp.

## 2. Ce am aflat
- **Fructele (Fruit Love Island, din 13 martie 2026):** microdrame zilnice facute integral cu AI. Fluxul descris:
  imagini de scena generate (Nano Banana) -> clipuri cu Veo 3.1 Fast / Kling / Runway -> montaj. E numit des
  "AI slop": ieftin, usor de copiat, construit pe timp de vizionare.
- **Cadrele noastre sunt scurte (1,5-2,6 s, media 1,9 s).** Avantaj: un clip AI scurt deriva mai putin, iar
  personajele raman mai consistente. Dezavantaj: modelele genereaza minim 4-5 s, deci platim ~2x durata.
- **Stilul nostru e prietenos cu AI:** personaje cubice, fete-decal fara mimica, decoruri simple. Mult mai usor
  de tinut consistent decat oameni realisti.
- **Laptopul tau** (RTX 3050 Ti 4 GB, i7-11800H, 16 GB RAM): ajunge pentru Blender/Roblox Studio, NU pentru
  modele video AI locale (cer 16-24 GB VRAM). Deci AI video = prin API, platit pe secunda.
- **Piata se misca repede:** Veo 3.1 preview a fost oprit pe 22 oct 2026 (inlocuit de Gemini Omni Flash),
  API-ul Sora e programat pentru retragere. Codul trebuie sa permita schimbarea furnizorului dintr-o setare.

## 3. Metodele posibile

| | A. AI imagini + image-to-video (recomandat) | B. Blender automatizat | C. Roblox Studio automatizat | D. "Motion comic" |
| --- | --- | --- | --- | --- |
| Cum | imagine-cheie per cadru (cu referinte de personaj) -> clip AI de 4-5 s -> taiat la durata cadrului | scene construite din cod Python (bpy): personaje, camera, clipuri de miscare, schimbat decal-ul fetei, randare Eevee | scripturi Luau prin MCP-ul oficial Studio: personaje, animatii din catalog, camera, inregistrare ecran | doar imaginile-cheie, cu zoom/pan/parallax din ffmpeg |
| Calitate | cea mai "cinematica" (lumina, VFX, DOF gratis) | curata, consistenta 100%, miscare limitata la biblioteca | aspect Roblox autentic, dar miscare rigida | slaba pentru format |
| Consistenta personaje | buna cu referinte, nu perfecta | perfecta | perfecta | buna |
| Cost / video | ~$5-17 | ~$0 (curent) | ~$0 | ~$1-2 |
| Timp / video | 15-40 min (generare in paralel) + alegere | 20-50 min randare pe laptop | timp real + montaj | minute |
| Efort de constructie | mic-mediu (1-2 saptamani) | mare (3-6 saptamani) | mare, fragil | mic |
| Risc principal | politica YouTube pe AI, filtre de continut, furnizori care se schimba | "actorie" slaba, mult cod | Studio nu are randare offline, automatizare grea | nu tine atentia |

## 4. Recomandarea: A, cu D ca plasa de siguranta
De ce A:
1. Se potriveste perfect cu ce avem: `shots.json` are deja pentru fiecare cadru decor, lumina, personaje,
   expresie, camera, actiune, VFX si durata exacta. Promptul video se construieste direct din el.
2. Cost de 5-10 ori mai mic decat animatorul si fara asteptare.
3. Calitatea vizuala (bloom, particule, profunzime de camp) vine gratis, iar la canalul de referinta e un punct forte.
4. E metoda dovedita de piata (fructele).

D (motion comic) costa aproape nimic si foloseste aceleasi imagini-cheie: e util ca test rapid al povestii,
inainte sa platim clipurile.

B ramane optiunea daca A pica la consistenta sau la politica YouTube.

## 5. Cum intra in pipeline
Pasii noi, intre `prep` si `final` (care ramane neschimbat si primeste `render.mp4` ca acum):

1. **`library`** (o singura data): fise de personaj (fata, profil, spate, 3/4) pentru `hero` si fiecare personaj
   din `config.yaml`, plus cate o imagine de referinta per decor si lumina. Salvate in `assets/library/`.
   Inlocuiesc "builder-ul" din planul initial.
2. **`keyframes <slug>`**: pentru fiecare cadru din `shots.json`, o imagine 9:16 generata cu referintele
   personajelor si decorului din cadru (Nano Banana 2.1, ~$0.03-0.05 / imagine). 2 variante per cadru.
3. **Punct de control uman**: alegi imaginile in `keyframes.html` (sau pe Telegram, mai tarziu cu n8n).
4. **`clips <slug>`**: image-to-video per cadru, 9:16, 720p, 4-5 s, prompt = actiunea + miscarea de camera +
   VFX. Audio-ul generat de model se arunca (avem master.wav).
5. **`assemble <slug>`**: fiecare clip taiat (sau usor accelerat) la durata exacta a cadrului din `timings.json`,
   lipite -> `render.mp4` 1080x1920 30 fps. Apoi `final` ca pana acum.

Schimbari mici in rest:
- Promptul de script: **o singura actiune vizuala per cadru** (acum unele cadre au doua: "farfuria se repara SI
  geamul se crapa" nu incape in 2 s).
- Furnizorul video si modelul: setari in `config.yaml`, nu in cod.
- Fiecare imagine si clip se salveaza cu promptul si furnizorul (dovada a procesului creativ, utila si pentru
  YouTube si pentru licente).

## 6. Cost estimat per video (35 s, 18 cadre)
Preturile vin din surse mixte (oficiale + revanzatori) si se schimba des; le verificam in pilot.

| Element | Calcul | Cost |
| --- | --- | --- |
| Imagini-cheie | 18 cadre x 2 variante x ~$0.034 | ~$1.2 |
| Clipuri, model ieftin (Hailuo, ~$0.04/s) | 18 x 4 s x 1,5 (refaceri) | ~$4.3 |
| Clipuri, model mediu (Omni Flash / Veo Fast / Kling, ~$0.08-0.12/s) | 18 x 4 s x 1,5 | ~$9-13 |
| Clipuri, model scump (Seedance / Veo standard, ~$0.15-0.40/s) | 18 x 4 s x 1,5 | ~$16-43 |
| Voce + muzica + efecte (ElevenLabs Starter) | deja platit lunar | ~$0.2 |

La 1 video/zi, cu un model mediu: ~$300-400/luna, fata de ~$1.650-3.300 cu animatori.

## 7. Riscuri si cum le tratam
- **Consistenta personajelor intre cadre**: fise de personaj ca referinta la fiecare imagine, design simplu
  (cubic, culori plate, decal), clipuri scurte, alegere umana a variantelor. In pilot masuram cate cadre
  trebuie refacute.
- **Filtre de continut pentru copii (UE)**: la Veo, image-to-video permite doar "adulti" in UE (inclusiv
  Romania), iar eroul nostru e un copil. Personajele cubice s-ar putea sa treaca, dar trebuie testat.
  Alternative: alti furnizori (Kling, Hailuo, Seedance) sau personaje fara varsta clara.
- **Politica YouTube "continut neautentic"**: AI-ul in sine nu e interzis; problema e continutul produs in
  masa, pe sablon. Aparare: povesti originale, personaje proprii, variatie, aprobare umana la script, la
  imagini si la final. Animatia vizibil animata nu cere eticheta "AI realist".
- **"Roblox"**: descriem stilul ("blocky toy-like 3D characters"), fara logo-uri sau nume de marca in imagini.
- **Furnizori care dispar sau se scumpesc**: un strat mic de adaptor per furnizor, ales din `config.yaml`.
- **Cost scapat de sub control**: limita de buget per video in config; generarea se opreste cand e atinsa.

## 8. Pilotul (o saptamana)
1. Creezi conturile si cheile (punctul 9).
2. Construiesc `library` (fisele lui `hero`, `mom`, `brother`, decorurile din scriptul "sorry").
3. `keyframes` pe cele 18 cadre: verificam consistenta pe imagini (ieftin) inainte de video.
4. `clips` cu 2 furnizori pe aceleasi imagini: Google (Omni Flash / Veo) si unul prin fal.ai (Kling sau Hailuo).
5. `assemble` + `final` -> doua video-uri complete, puse unul langa altul.
6. Decizie pe criterii: personaj recognoscibil in >= 15 din 18 cadre, maxim 2 refaceri per cadru, cost
   <= $15/video, timp <= 1 ora inclusiv alegerea ta.

## 9. Ce trebuie sa faci tu
- Cont **Google AI Studio** cu facturare activa -> cheie API (pentru Nano Banana si Omni Flash / Veo).
- Cont **fal.ai** (un singur cont pentru Kling, Hailuo, Seedance si altii) -> cheie API.
- Cheile se pun in `.env`, ca la ElevenLabs. Le adaug in `.env.example`.
- Un buget de test: ~$20-30 pentru tot pilotul.

## Surse
- NBC News, Fruit Love Island: https://www.nbcnews.com/pop-culture/viral/ai-fruit-love-island-tiktok-slop-popularity-rcna264946
- Wikipedia, Fruit Love Island: https://en.wikipedia.org/wiki/Fruit_Love_Island
- Thairath, "Unfaithful Fruit": https://en.thairath.co.th/lifestyle/life/2932762
- software.informer, The Slop Opera: https://software.informer.com/Stories/the-slop-opera-why-ai-fruit-dramas-took-over-tiktok.html
- Filmora, cum se fac: https://filmora.wondershare.com/video-editing-tips/fruit-drama-ai.html
- Google, documentatia Veo (durate, 9:16, referinte, restrictii UE): https://ai.google.dev/gemini-api/docs/veo
- Google, preturi Gemini API (imagini): https://ai.google.dev/gemini-api/docs/pricing
- Preturi video comparate: https://invideo.io/blog/ai-video-model-pricing/ , https://apiframe.ai/blog/ai-video-api-pricing-2026 , https://www.cometapi.com/ai-video-api-pricing/
- Gemini Omni Flash: https://venturebeat.com/technology/googles-gemini-omni-flash-hits-the-api-turning-enterprise-video-production-into-a-conversation , https://www.eesel.ai/blog/gemini-omni-flash-pricing
- Kling 3.0: https://evolink.ai/blog/kling-3-api-pricing-integration-guide , https://www.krea.ai/blog/kling-3-0-api-access-guide-pricing-code-examples-for-multi-shot-ai-video
- Seedance 2.0: https://www.atlascloud.ai/blog/guides/seedance-2.0-api-pricing-the-cheapest-provider-compared
- Consistenta personajelor: https://magichour.ai/blog/how-to-keep-characters-consistent-in-ai-video
- Roblox Studio MCP: https://create.roblox.com/docs/studio/mcp
- YouTube si AI: https://www.eweek.com/news/youtube-responds-to-ai-concerns/ , https://www.netinfluencer.com/youtube-clarifies-july-15-policy-update-repetitious-content-rebranded-as-inauthentic-content/
