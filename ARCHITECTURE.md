# Mimari

Bu belge motorun katmanlarını, veri akışını ve hakem protokolünü açıklar.
İddialar koddan doğrulanabilir; doğrulanamayan hiçbir teknoloji burada
listelenmez.

## Genel bakış

```mermaid
graph TB
    subgraph Client["1. İstemci"]
        CLI["CLI<br/>engine/cli.py"]
        WebUI["Statik Web Paneli<br/>web/index.html"]
    end

    subgraph API["2. Arayüz"]
        REST["ThreadingHTTPServer<br/>engine/server.py<br/>127.0.0.1, CORS sınırlı"]
    end

    subgraph Core["3. Orkestrasyon"]
        SE["SearchEngine<br/>engine/search_engine.py<br/>fetcher enjeksiyonu + teşhis"]
        CFG["config.py<br/>URL, timeout, eşikler"]
        LOG["logging_setup.py"]
    end

    subgraph Fetch["4. Veri Toplama — 18 kaynak"]
        Live["9 CANLI kaynak<br/>TDK · Nişanyan · EtimolojiTürkçe<br/>Wiktionary ×2 · Wiktextract · Archive.org"]
        Seed["9 TOHUM veri dosyası<br/>data/seed/ — 59 kayıt<br/>Clauson · ÉSTJa · DLT · Starling · Tietze"]
        HTTP["Ortak HTTP istemcisi<br/>utils/network.py<br/>retry · SSRF koruması · teşhis"]
    end

    subgraph NLP["5. Hesaplamalı Dilbilim"]
        Recon["Karşılaştırmalı rekonstrüksiyon<br/>nlp/comparative_reconstruction.py"]
        Align["Fonetik hizalama<br/>nlp/cldf_lingpy_aligner.py (LingPy SCA)"]
        Phon["Artikülatör özellikler<br/>nlp/phonological_feature_engine.py (PanPhon)"]
        Loan["Alıntı keşif hattı — 4 katman<br/>nlp/loanword_detector.py"]
        Clust["Akraba kümeleme<br/>nlp/cognate_clustering.py"]
        Morph["Tarihsel ek ağacı<br/>nlp/historical_morphology.py"]
        SLI["Ses kanunu indüksiyonu<br/>nlp/sound_law_induction.py"]
    end

    subgraph AHVP["6. A-HVP Hakem Protokolü"]
        S1["Aşama 1 · Fonetik zincir (%35)"]
        S2["Aşama 2 · Kronoloji (%30)"]
        S3["Aşama 3 · Semantik mesafe (%15)"]
        S4["Aşama 4 · Triangulation (%20)"]
        Cover["Kanıt kapsamı normalizasyonu"]
    end

    subgraph Persist["7. Kalıcılık ve Dışa Aktarım"]
        DB["SQLite + TTL önbellek<br/>db/database.py"]
        Graph["Cytoscape graf üretici<br/>db/graph_database.py"]
        CLDF["CLDF içe/dışa aktarım<br/>db/cldf_exporter.py · cldf_importer.py"]
    end

    subgraph LLM["8. Opsiyonel LLM"]
        Qwen["Ollama sentezi<br/>llm/qwen_agent.py"]
    end

    CLI --> SE
    WebUI --> REST --> SE
    CFG --> SE
    LOG --> SE
    SE --> Live & Seed
    Live --> HTTP
    SE --> Recon & Loan & Clust & Morph & SLI
    Recon --> Align --> Phon
    Recon --> S1
    SE --> S2 & S3 & S4
    S1 & S2 & S3 & S4 --> Cover
    Cover --> SE
    SE --> DB & Graph & CLDF
    SE -.opsiyonel.-> Qwen
```

## Katmanlar

| Katman | Dosya | Sorumluluk |
|---|---|---|
| Yapılandırma | `engine/config.py` | Tüm URL, timeout, port, model adı, eşik ve ağırlıklar. `ETY_*` ortam değişkenleriyle ezilebilir. |
| Loglama | `engine/logging_setup.py` | Merkezî logger; her yutulan hata görünür olur. |
| Orkestrasyon | `engine/search_engine.py` | Fetcher paralelleştirme, teşhis toplama, NLP zinciri, önbellek. Fetcher listesi enjekte edilebilir (`fetchers=`). |
| HTTP | `engine/utils/network.py` | Tek HTTP kapısı: retry/backoff, tek User-Agent, SSRF koruması, charset sezimi, istek bazlı teşhis. |
| Veri toplama | `engine/fetchers/` | 18 toplayıcı + `BaseFetcher` sözleşmesi. Sözleşme: `fetch()` asla istisna fırlatmaz. |
| Dilbilim | `engine/nlp/` | Rekonstrüksiyon, hizalama, kümeleme, alıntı keşfi, A-HVP. |
| Ortak kurallar | `engine/utils/phonotactics.py`, `orthography.py` | Fonotaktik kısıtlar, ünlü uyumu, alıntı dil kalıpları, Türki Kiril karakter sınıfı. |
| Kalıcılık | `engine/db/` | SQLite (TTL önbellekli), Cytoscape graf, CLDF içe/dışa aktarım. |
| LLM | `engine/llm/` | Ollama sentezi. Kazınmış içerik `<untrusted_source>` sınırlayıcılarıyla verilir. |

## Veri akışı

```mermaid
sequenceDiagram
    participant U as Kullanıcı
    participant SE as SearchEngine
    participant DB as SQLite
    participant F as 18 Fetcher
    participant N as NLP
    participant A as A-HVP

    U->>SE: search("göz")
    SE->>DB: get_finding(word, max_age=TTL)
    alt Önbellekte taze kayıt var
        DB-->>SE: kayıtlı bulgu
        SE-->>U: from_cache = true
    else Önbellek ıskası
        SE->>SE: morfolojik ayrıştırma + varyant üretimi (MAX_VARIANTS ile sınırlı)
        par Paralel toplama (ThreadPoolExecutor)
            SE->>F: fetch(varyant)
            F-->>SE: kayıtlar + kaynak teşhisi (süre, durum, hata)
        end
        SE->>N: karşılaştırmalı rekonstrüksiyon (gerçek akraba kayıtlarıyla)
        N-->>SE: ata biçim + kanıta dayalı güven
        SE->>N: alıntı keşif hattı (4 katman)
        SE->>N: akraba kümeleme + tarihsel ek ağacı + ses kanunu indüksiyonu
        SE->>A: hipotez doğrulama
        A-->>SE: rozet + skor + evidence_coverage + eksik aşamalar
        SE->>DB: save_finding
        SE-->>U: bulgu + diagnostics (gerçek aşama süreleri)
    end
```

## Karşılaştırmalı rekonstrüksiyon

Ata biçim, akraba biçimlerin hizalanmasıyla **konum duyarlı denklik
kümelerinden** türetilir:

| Konum | Denklik | Ata ses | Örnek |
|---|---|---|---|
| söz başı | `d ~ t` | `*t-` | deniz ~ теңіз → `*teŋiŕ` |
| söz başı | `g ~ k` | `*k-` | göz ~ көз → `*köŕ` |
| söz başı | `y ~ c ~ j ~ ç` | `*j-` | yol ~ жол ~ ҫул → `*jol` |
| söz sonu | `z ~ r` | `*-ŕ` | Lir-Şaz rotasizmi |
| söz sonu | `ş ~ l` | `*-ĺ` | lambdaizm |
| her yer | `n ~ ŋ` | `*-ŋ-` | deniz ~ teŋiz |

Güven skoru üç bileşenden hesaplanır:

```
güven = 0.40 × (tanık sayısı / 6)      # kaç bağımsız dil
      + 0.30 × (kol sayısı / 4)        # Oğuz, Kıpçak, Karluk, Sibirya, Oğur
      + 0.30 × sütun uyumu             # hizalama sütunlarında tanıkların uzlaşması
```

En az **iki bağımsız dil tanığı** yoksa ata biçim üretilmez.

## A-HVP hakem protokolü

```mermaid
flowchart TD
    H[Hipotez] --> S1 & S2 & S3 & S4

    S1["Aşama 1 · Fonetik zincir<br/>sıralı dizi hizalaması + yön denetimli ses kanunları"]
    S2["Aşama 2 · Kronoloji<br/>donör temas dönemi vs ilk tanıklama yılı"]
    S3["Aşama 3 · Semantik mesafe<br/>tarihsel anlam ↔ modern anlam"]
    S4["Aşama 4 · Triangulation<br/>gerçek lehçe yayılımı + kaynak çeşitliliği"]

    S1 --> C{Kanıt üretebildi mi?}
    S2 --> C
    S3 --> C
    S4 --> C

    C -->|hayır| D[Aşama ağırlığı toplamdan DÜŞÜLÜR]
    C -->|evet| E[Ağırlıklı skora katılır]

    D --> N[evidence_coverage hesaplanır]
    E --> N
    N --> V{kapsam ≥ %50?}
    V -->|hayır| IE["⚪ YETERSİZ KANIT"]
    V -->|evet| R{ihlal var mı?}
    R -->|evet| RJ["🔴 REDDEDİLDİ"]
    R -->|hayır| SC{aşama skoru}
    SC -->|≥ 0.75| OK["🟢 DOĞRULANDI<br/>(kapsam bildirilir)"]
    SC -->|≥ 0.50| NR["🟡 İNCELEME GEREKLİ"]
    SC -->|< 0.50| RJ2["🔴 REDDEDİLDİ"]
```

**Skor formülü**

```
aşama_skoru = Σ(ağırlık_i × skor_i) / Σ(ağırlık_i)      # yalnızca kanıtlı aşamalar
kapsam      = Σ(ağırlık_i) / Σ(tüm ağırlıklar)
yayımlanan  = aşama_skoru × kapsam
```

`aşama_skoru` ölçülebilen kanıtın **kalitesini**, `kapsam` ne kadarının
ölçülebildiğini bildirir. Rozet kararı `aşama_skoru` üzerinden verilir;
`kapsam` bir kapı görevi görür. Böylece "kanıt eksik" ile "kanıt kötü"
birbirine karışmaz.

## Alıntı keşif hattı

`nlp/loanword_detector.py` dört katmanı uygular:

1. **Fonotaktik ihlal analizi** — söz başı ünsüz kısıtı, ünsüz kümesi, ünlü
   uyumu (bileşikler istisna), Arapça vezin, Farsça/Batı ekleri
2. **Çapraz lehçe yayılımı** — gerçek `lang_code` sayımı / 25 dil
3. **Olasılık dağılımı** — öz Türkçelik ile donör atfı ayrı hesaplanır
4. **Donör en-yakın-komşu** — IPA Levenshtein ≤ 2

Katman 4 doğrudan eşleşme bulursa sınıflandırma ona uyar: sözlük kanıtı
kural tabanlı tahmini ezer.

## Graf şeması

`db/graph_database.py` Neo4j şemasına uygun düğüm/kenar üretir ve Cytoscape.js
JSON'u olarak dışa verir. **Neo4j sürücüsü kullanılmaz; canlı bir graf
veritabanı bağlantısı yoktur.**

| Düğüm | Alanlar |
|---|---|
| `WordForm` | word, lang, script |
| `ProtoRoot` | word, lang |
| `EtymologyCase` | hypothesis_type, confidence_score *(kanıt yoksa `null`)* |
| `Attestation` | kaynak, yıl |

| Kenar | Anlam |
|---|---|
| `DERIVED_FROM` | ata kök → modern biçim |
| `HAS_HYPOTHESIS` | kelime → etimoloji vakası |
| `ATTESTED_IN` | kelime → tarihsel tanıklama |
| `COGNATE_OF` | ata kök → akraba biçim |

Düğüm kimlikleri sanitize edilir; boşluk veya özel karakter içeren kelimeler
bozuk seçici üretmez.

## Güvenlik

| Yüzey | Önlem |
|---|---|
| Sunucu bağlanma | Varsayılan `127.0.0.1`; yerel olmayan adres uyarı loglar |
| CORS | Yapılandırılmış origin listesi; `*` varsayılan değil |
| Hata sızıntısı | İç istisna metni istemciye gitmez (`ETY_API_DEBUG_ERRORS` ile açılır) |
| Girdi | `MAX_QUERY_LENGTH` sınırı, amplifikasyon için `MAX_VARIANTS` |
| SSRF | `utils/network.py` özel/loopback/link-local adresleri ve `http(s)` dışı şemaları reddeder; kazıyıcılar alan adı beyaz listesi kullanır |
| Prompt injection | Kazınmış içerik `<untrusted_source>` içinde, uzunluğu sınırlı, sınırlayıcı etiketler kaçırılır |
| Web paneli XSS | Tüm dinamik içerik HTML kaçışından geçer; CDN betiklerinde SRI |

## Test mimarisi

```
engine/tests/
  conftest.py          soket düzeyinde ağ yalıtımı, geçici DB, tohum izolasyonu
  fakes.py             BaseFetcher test ikizleri (Fake/Failing/Empty/Slow)
  fixtures/http/       canlı kaynaklardan kaydedilmiş gerçek yanıtlar
  test_*.py            323 ağsız test
  live/                9 canlı kaynak testi (ETY_LIVE=1)
```

Testler soket düzeyinde ağdan yalıtılır: yanlışlıkla canlı ağa çıkan bir test
açık bir hata alır. `responses` ile mock'lanan istekler soket açmadığı için geçer.

## Bilinçli kapsam dışı bırakılanlar

| Konu | Gerekçe |
|---|---|
| Eğitilmiş ML alıntı sınıflandırıcı | Etiketli Türkçe veri kümesi yok; WOLD ingest'i önce tamamlanmalı |
| FastText semantik benzerlik | `gensim`'in Python 3.14 tekerleği yok |
| Neo4j canlı bağlantı | Yerel araç için gereksiz karmaşıklık; şema uyumu korunuyor |
| Next.js web uygulaması | Tek dosyalık statik panel yeterli |
| loanpy, Zemberek, Starlang KeNet | Değerlendirildi, ertelendi |
