# Dokumentácia interpretu jazyka SOL26

**Autor:** Jakub Glončák (xgloncj00@stud.fit.vut.cz)  
**Predmet:** IPP 2025/2026  
**Implementačný jazyk:** Python 3.14

---

## Celkový popis návrhu riešenia

Interpreter prijíma program v jazyku SOL26 vo forme XML (SOL-XML), validuje jeho štruktúru, vykoná statické sémantické kontroly a potom interpretuje program metódou obchádzania stromu (tree-walking interpreter). Vstupný XML strom sa najskôr deserializuje pomocou knižnice `pydantic` do typovaného objektového modelu (`input_model`). Následne sa nad týmto modelom spustia statické kontroly a až potom začne samotná interpretácia odoslaním správy `run` inštancii triedy `Main`.

Celý interpreter je rozdelený do niekoľkých vzájomne prepojených modulov: `interpreter.py` (hlavná logika), `sol_objects.py` (runtime objekty), `class_table.py` (tabuľka tried), `environment.py` (premenné a scoping), `builtins.py` (vstavaná logika) a `static_checks.py` (sémantické kontroly).

Spracovanie prebieha v troch fázach: (1) načítanie a validácia XML vstupu pomocou `lxml` a `pydantic`, (2) statické sémantické kontroly, (3) rekurzívna interpretácia AST-u.

---

## UML diagram tried

```
┌──────────────────────┐
│      SOLObject       │  <<abstract>>
│─────────────────────│
│ + class_name: str    │
│ + attributes: dict   │
│ + sol_as_string()    │
└──────────┬───────────┘
           │  <<extends>>
   ┌───────┴──────────────────────────────────────────────┐
   │          │          │          │         │            │
┌──┴────┐ ┌───┴───┐ ┌────┴───┐ ┌───┴───┐ ┌───┴───┐ ┌─────┴──────┐
│SOLNil │ │SOLBool│ │SOLInt. │ │SOLStr.│ │SOLBlk │ │SOLInstance │
└───────┘ └───────┘ └────────┘ └───────┘ └───┬───┘ └────────────┘
                                              │
                                    ┌─────────┴────────┐
                                    │  captured_env:   │
                                    │  Environment     │
                                    │  self_ref:       │
                                    │  SOLObject|None  │
                                    └──────────────────┘

┌──────────────────────┐       ┌───────────────────────┐
│    SuperWrapper      │       │      ClassTable       │
│─────────────────────│       │───────────────────────│
│ + real_obj: SOLObj   │       │ + user_classes: dict  │
│ + current_class: str │       │ + BUILTIN_PARENTS     │
│ + sol_as_string()    │       │ + register()          │
└──────────────────────┘       │ + get_parent()        │
                               │ + find_method()       │
                               │ + is_subclass_of()    │
                               │ + get_ancestors()     │
                               └───────────────────────┘

┌──────────────────────┐       ┌───────────────────────┐
│    Environment       │       │      Interpreter      │
│─────────────────────│       │───────────────────────│
│ + variables: dict    │       │ + class_table         │
│ + parent: Env|None   │       │ + current_program     │
│ + set()              │  ←──  │ + load_program()      │
│ + get()              │       │ + execute()           │
└──────────────────────┘       │ + _send_message()     │
        ↑ parent chain         │ + _invoke_block()     │
                               │ + _execute_block()    │
                               │ + _evaluate_expr()    │
                               └───────────────────────┘
```

> Triedy poskytnuté šablónou (`Program`, `ClassDef`, `Method`, `Block`, `Expr` z `input_model`) sú uvedené v skrátenej forme bez atribútov, ale so zachovaním väzieb. `Interpreter` používa `ClassTable` na vyhľadávanie metód a `Environment` na správu premenných. `SOLBlock` drží referenciu na `Environment` (zachytené prostredie – closure).

---

## Hlavné interné dátové štruktúry

**`SOLObject` a podtriedy** — Každý runtime objekt v interpretovanom programe je inštanciou niektorej z podtried `SOLObject`. Každý objekt drží slovník `attributes` (inštančné premenné nastavované za behu správami setter) a reťazec `class_name`. Špeciálnou podtriedou je `SOLBlock`, ktorý navyše ukladá zachytenú referenciu na prostredie (`captured_env`) a referenciu na `self` v čase vytvorenia bloku (`self_ref`), čo umožňuje statický lexikálny scoping podľa sekcie 1.2.7 špecifikácie.

**`ClassTable`** — Centrálny register všetkých tried programu. Vstavaná hierarchia (Object, Integer, String, True, False, Nil, Block, Transcript) je zakódovaná v triednom atribúte `BUILTIN_PARENTS`. Používateľské triedy sa do tabuľky registrujú pred spustením interpretácie. Metóda `get_ancestors()` vracia zoradený zoznam predkov, čo zjednodušuje prechádzanie dedičnostného reťazca.

**`Environment`** — Slovník premenných s reťazením rodičovských prostredí (linked scopes). Metóda `set()` pri priradení najskôr prehľadá celý reťazec rodičov — ak nájde existujúcu väzbu, aktualizuje ju tam; ak nie, vytvorí novú väzbu v aktuálnom prostredí. Tým sa zabezpečuje správna closure sémantika: blok vidí a môže meniť premenné svojho obklopujúceho kontextu.

**`SuperWrapper`** — Interný obal pre príjemcu správy `super`. Uchováva skutočný objekt (`real_obj`) a triedu, v ktorej bol `super` použitý (`current_class`). Vyhľadávanie metódy v `_send_message()` potom začína od rodiča `current_class`, nie od triedy samotného príjemcu.

---

## Využité návrhové vzory a princípy OOP

**Visitor / Tree-walking interpreter** — Trieda `Interpreter` implementuje vzor návštevníka. Metóda `_evaluate_expr()` rozhoduje podľa toho, ktorý atribút uzla `Expr` je vyplnený (`literal`, `var`, `block`, `send`), a deleguje na príslušnú pomocnú metódu. Tým sa dosahuje čistá separácia logiky vyhodnocovania od dátového modelu AST. Rozšírenie o nový typ výrazu vyžaduje len pridanie nového atribútu do `Expr` a jednej vetvy v `_evaluate_expr()`.

**Template Method (v `dispatch_builtin`)** — Funkcia `dispatch_builtin()` v `builtins.py` najprv volá `_dispatch_object()` (metódy zdedené všetkými objektmi), a potom na základe typu príjemcu deleguje na špecializovaný dispatcher (`_dispatch_integer()`, `_dispatch_string()`, `_dispatch_bool()`, …). Zodpovedá hierarchickej dedičnosti SOL26 a odstraňuje duplicitu kódu — správy ako `asString`, `print`, `isNil` sa implementujú len raz.

**Chain of Responsibility (v `_send_message`)** — Hlavný dispatch prechádza postupne sedem úrovní zodpovednosti: správy triedy → rozvinutie `SuperWrapper` → Block dispatch → vyhľadávanie metód v dedičnostnej hierarchii → vstavaná logika → getter atribútu → setter atribútu. Každá úroveň buď spracuje správu a vráti výsledok, alebo odovzdá spracovanie ďalšej. Tento prístup jasne oddeľuje rôzne mechanizmy dispatchingu a umožňuje ich nezávislé rozširovanie.

**Prototype / Shallow copy (v `from:`)** — Správa `ClassName from: obj` vytvorí novú inštanciu ako plytkú kópiu existujúceho objektu skopírovaním `attributes` cez `dict(obj.attributes)`. Tým sa imituje prototypový vzor bez nutnosti explicitných klonovacích metód na každej triede.

---

## Problémy a ich riešenia

**Statický scoping `self` v blokoch** — Podľa sekcie 1.2.7 špecifikácie musí blok pri zavolaní vidieť `self` z miesta, kde bol vytvorený, nie z miesta volania. Problém nastáva, keď sa blok predá inej metóde alebo objektu a zavolá sa z iného kontextu. Riešenie: `SOLBlock` si pri vytváraní uloží aktuálny `self` do `self_ref`. Metóda `_invoke_block()` ho pred spustením bloku explicitne nastaví do prostredia bloku, čím prepíše prípadný `self` z rodičovského kontextu.

**`super` ako príjemca správy vs. ako hodnota argumentu** — Špecifikácia stanovuje, že `super` použitý ako argument alebo pravá strana priradenia sa správa rovnako ako `self`, ale ako príjemca správy musí spustiť vyhľadávanie od rodičovskej triedy. Bolo potrebné rozlíšiť tieto dva prípady bez zmeny gramatiky jazyka. Riešenie: `SuperWrapper` obalí skutočný objekt; v `_send_message()` sa argumenty typu `SuperWrapper` okamžite rozvinú na `real_obj`, kým pri príjemcovi sa extrahuje `current_class` pre nastavenie štartovného bodu vyhľadávania.

---

## Možnosti ďalšieho rozšírenia

**Prísnejšia typová kontrola pri `from:`** — Aktuálne riešenie pri volaní `SubClass from: instance` kopíruje atribúty, ale neoveruje kompatibilitu typovej hierarchie v plnom rozsahu. Vďaka existujúcej metóde `ClassTable.is_subclass_of()` by bolo možné pridať triedu `TypeChecker` s metódou `is_compatible_for_copy(source_class, target_class)`, ktorá by prechádzala dedičnostný reťazec a overovala kompatibilitu bez zásahu do ostatného kódu.

**Podpora výnimiek (napr. `signal`, `on:do:`)** — Jazyk SOL26 momentálne výnimky nepodporuje. Ich pridanie by vyžadovalo novú podtriedu `SOLException(SOLObject)` a mechanizmus rozvíjania zásobníka volaní. Vďaka hierarchii `SOLObject` stačí pridať novú podtriedu; šírenie výnimky by mohlo byť implementované ako Python výnimka zachytávaná v `_send_message()`, čím by sa minimalizoval zásah do existujúcej štruktúry.

---

## Využitie AI nástrojov

Pri riešení projektu bol využitý asistent **Perplexity AI** (model Claude Sonnet). Asistent slúžil výhradne ako podpora pri:

- dovysvetlení nejasností v zadaní (napr. správanie `super` ako argumentu, scoping `self` v blokoch podľa sekcie 1.2.7),
- konzultácii pri návrhu vysokoúrovňovej architektúry (rozdelenie do modulov),
- hľadaní konkrétnych chýb vo vlastnom napísanom kóde,
- kontrole pravopisu, gramatiky a štylistiky tejto dokumentácie.

Celá implementácia bola vypracovaná autorom; AI nástroj negeneroval celé časti kódu. Záznamy konverzácií sú priložené v súbore `ai-perplexity.md`.
