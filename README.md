# EUGM oldalszerkesztő

Az eugm.hu mind a 15 oldalának szerkeszthető makettje (Szerkesztő / Megjelenítő mód, elemek húzása,
szövegek és hirdetések átírása, saját képek, képillesztés).

- `index.html` – a teljes alkalmazás egyetlen fájlban
- `eugm-adatok.json` – az oldalak tartalma (az alkalmazás ezt tölti be induláskor)

A „Mentés fájlba” gomb a módosított oldalt HTML-fájlként tölti le. Ha a módosított tartalmat
élesíteni szeretné, a letöltött fájlból a ⋯ menü „Tartalom betöltése mentett fájlból…” pontjával
tölthető vissza, vagy a benne lévő `eugm-data` tartalom kerülhet az `eugm-adatok.json`-ba.
