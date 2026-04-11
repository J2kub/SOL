**Zadání:**

> Stupeň `build` (příp. `build-test`) – vyžadován pouze pro TS – provede překlad zdrojového kódu interpretu/testovacího nástroje. Budeme automaticky analyzovat výstup překladače, je proto důležité, abyste neměnili v šabloně použitou konfiguraci překladu.

V případě částí projektů implementovaných v jazyce TypeScript tedy spustíme sestavení obrazu kontejneru a budeme zachytávat standardní chybový výstup, na který Docker vypisuje výstupy z příkazů, které jsou při provádění Containerfile volány:


```sh
cd rozbaleny_projekt_xlogin0b/
docker build --target build --progress plain . 2>xlogin0b_build.log
```

Váš Containerfile musí někdy v průběhu stupně `build` spustit překlad TS kódu, např.:

```dockerfile
RUN tsc --project tsconfig.json
```

Pozor, výstup tohoto příkazu nesmí být někam přesměrován/potlačen.

Ve výsledném logu pak budou automaticky vyhledávána chybová hlášení či upozornění překladače TS.