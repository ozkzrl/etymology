# Türki Diller Etimoloji Araştırma Motoru

Yerel çalışan, kaynak-şeffaf bir etimoloji araştırma motoru. Bir Türkçe kelimenin
Türki dillerdeki karşılıklarını toplar, **karşılaştırmalı yöntemle** Proto-Türkçe
ata biçimini türetir, alıntı olup olmadığını sınıflandırır ve ürettiği her
hipotezi dört aşamalı bir hakem protokolünden geçirir.

Temel ilke: **kanıt yoksa puan da yok.** Motor bir sonucu ancak ölçebildiği
kanıt kadar destekler; ölçemediği aşamayı skora katmaz ve eksikliği açıkça
raporlar.

```
$ python -m engine.cli search göz

  Ana Kök / Rekonstrüksiyon : *köŕ
  Yöntem                    : karşılaştırmalı yöntem, 8 dil tanığı / 5 Türki kol
  Uygulanan denklikler      : g- ~ k- (Proto-Türkçe *k-)
                              Ortak Türkçe -z ~ Çuvaşça -r (Lir-Şaz rotasizmi)
  Hakem kararı              : 🟢 DOĞRULANDI — kısmi kanıt, %85 kapsam
  Alıntı sınıfı             : Asli Öz Türkçe (Native Turkic)
```

## Kurulum

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                 # çekirdek + test araçları
pip install -e ".[dev,phon,pdf]"        # + LingPy, PanPhon, Epitran, pdfminer
```

| Ekstra | İçerik | Zorunlu mu? |
|---|---|---|
| *(çekirdek)* | `requests` | evet |
| `phon` | `lingpy`, `panphon`, `epitran` — gerçek fonetik hizalama ve IPA | hayır, ama önerilir |
| `pdf` | `pdfminer.six` — `data/books/` altındaki PDF'lerde tam metin arama | hayır |
| `semantic` | `sentence-transformers` — semantik mesafe aşaması (~2-3 GB) | hayır |
| `dev` | `pytest`, `pytest-cov`, `responses`, `ruff` | geliştirme |

Bu ekstralar kurulu değilse motor çökmez: ilgili aşama **kanıt üretmediğini
bildirir** ve skora katılmaz.

## Kullanım

```bash
python -m engine.cli search deniz              # arama
python -m engine.cli search deniz --json       # ham JSON
python -m engine.cli search deniz --ai         # + yerel LLM sentezi (Ollama)
python -m engine.cli validate göz --origin '*köŕ' --donor 'Proto-Türkçe'
python -m engine.cli list                      # kayıtlı bulgular
python -m engine.cli show göz                  # kayıtlı bulguyu göster
python -m engine.cli export göz --out cldf/    # CLDF dışa aktarım
python -m engine.cli bulk --file kelimeler.txt # toplu sorgu
python -m engine.cli search göz --verbose      # ayrıntılı log
```

### REST API ve web paneli

```bash
python -m engine.server            # http://127.0.0.1:8000
cd web && npx serve -l 3000 .      # http://localhost:3000
```

| Uç nokta | Açıklama |
|---|---|
| `GET /api/search?word=X&ai=false&save=true` | Etimoloji araması |
| `GET /api/list` | Kayıtlı bulgular |
| `GET /api/health` | Kaynak sayıları ve önbellek durumu |

Sunucu varsayılan olarak **yalnızca `127.0.0.1`** dinler ve CORS'u
yapılandırılmış origin'lerle sınırlar. Kimlik doğrulaması yoktur; dışa açmayın.

## Veri kaynakları

Motor **9 canlı kaynak** ve **9 yerel tohum (seed) veri dosyası** kullanır.
İkisi arasındaki fark her kayıtta `origin: "live" | "seed"` alanıyla,
CLI ve web panelinde ise görsel olarak belirtilir.

**Canlı kaynaklar** — TDK (Güncel Türkçe Sözlük, Tarama, Derleme), Nişanyan
Sözlük, EtimolojiTürkçe (tarihli ilk tanıklamalar), İngilizce Wiktionary
(kelime sayfası + Proto-Turkic rekonstrüksiyon sayfaları), 14 Türki dilin kendi
Wiktionary sürümü, Wiktextract/Kaikki, Internet Archive.

**Tohum veri** (`data/seed/`) — Clauson EDPT, Sevortjan ЭСТЯ, Divânu Lugâti't-Türk,
Kamûs-ı Türkî, Codex Cumanicus, Starling Altaic, Tietze, İSAM, Kubbealtı ve
donör dil kayıtlarından elle derlenmiş **toplam 59 kelimelik** çekirdek veri.
Her dosya kaynak künyesi (`_provenance`) taşır. Bu veri canlı bir servis
değildir ve öyle sunulmaz.

> Ölü uç noktalar (Glosbe API, TDK TTAS/Kişi Adları, DergiPark arama) portföyden
> **çıkarılmıştır**. Kaynak sayısını korumak için çalışmayan fetcher tutulmaz.

## Nasıl çalışır

```
kelime
  │
  ├─ 1. Morfolojik ayrıştırma  ──────────  utils/morphology, nlp/historical_morphology
  │        güzellik -> güzel +lIK ;  göz -> gö- + -z
  │
  ├─ 2. Paralel veri toplama  ───────────  18 fetcher, ThreadPoolExecutor
  │        varyantlar sınırlı (MAX_VARIANTS), her istek teşhis defterine yazılır
  │
  ├─ 3. Karşılaştırmalı rekonstrüksiyon ─  nlp/comparative_reconstruction
  │        konum duyarlı denklik kümeleri: söz başı d~t -> *t- ; söz sonu z~r -> *-ŕ
  │        güven = tanık sayısı + Türki kol çeşitliliği + sütun uyumu
  │
  ├─ 4. Alıntı keşif hattı  ─────────────  nlp/loanword_detector (4 katman)
  │        fonotaktik ihlaller -> lehçe yayılımı -> olasılık -> donör en-yakın-komşu
  │
  ├─ 5. A-HVP hakem protokolü  ──────────  nlp/hypothesis_validation_protocol
  │        4 aşama; kanıt üretemeyen aşama skordan DÜŞÜLÜR
  │
  └─ 6. Graf, CLDF, önbellek, LLM sentezi
```

### A-HVP: dört aşamalı hakem protokolü

| Aşama | Ağırlık | Ne ölçer | Kanıt yoksa |
|---|---|---|---|
| 1 · Fonetik zincir | %35 | Ata biçim ile modern biçim arasında düzenli ses denkliği | aşama düşülür |
| 2 · Kronoloji | %30 | Kaynak dil teması ilk tanıklamadan önce mi (anakronizm kilidi) | aşama düşülür |
| 3 · Semantik mesafe | %15 | Tarihsel anlam ile modern anlam arasındaki uzaklık | aşama düşülür |
| 4 · Akraba triangulation | %20 | Gerçek Türki dil karşılıklarının yayılımı ve kaynak çeşitliliği | aşama düşülür |

Skor, **yalnızca kanıt üretebilen aşamalara** normalize edilir. `evidence_coverage`
alanı kaç aşamanın konuşabildiğini bildirir; kapsam %50'nin altındaysa rozet en
fazla `⚪ YETERSİZ KANIT` olabilir.

```
göz    < *köŕ  (8 tanık, 5 kol)     -> 🟢 DOĞRULANDI — kısmi kanıt, %85 kapsam
kitap  < Arapça kitāb               -> 🟡 İNCELEME GEREKLİ
su     < Fransızca sous, 735 tanık  -> 🔴 REDDEDİLDİ (anakronizm)
zzzqx  < *zzzqx, kanıt yok          -> ⚪ YETERSİZ KANIT (%35 kapsam)
```

## Yapılandırma

Tüm ayarlar `engine/config.py` içinde toplanır ve `ETY_` önekli ortam
değişkenleriyle ezilebilir:

```bash
ETY_API_HOST=127.0.0.1 ETY_API_PORT=8000 python -m engine.server
ETY_MAX_VARIANTS=2 ETY_CACHE_ENABLED=false python -m engine.cli search göz
ETY_OLLAMA_MODEL=qwen2.5:7b python -m engine.cli search göz --ai
ETY_LOG_LEVEL=DEBUG python -m engine.cli search göz
```

## Geliştirme

```bash
make test        # ağsız test paketi (323 test, ~40 sn)
make test-live   # canlı kaynak testleri (ağ gerektirir)
make coverage    # kapsam raporu, %90 eşiği
make lint        # ruff
```

Testler **soket düzeyinde ağdan yalıtılır**: bir test yanlışlıkla canlı ağa
çıkmaya kalkarsa açık bir hata alır. Canlı kaynak testleri
`engine/tests/live/` altındadır ve yalnızca `ETY_LIVE=1` ile çalışır.

HTTP fixture'ları gerçek yanıtlardan kaydedilir:

```bash
python scripts/record_fixtures.py --live --word deniz --overwrite
```

## Harici veri kümesi içe alma

WOLD gibi CLDF veri kümelerinden alıntı kelime kayıtları alınabilir:

```bash
python -m engine.db.cldf_importer /path/to/wold-cldf --target-language tur
```

## Proje yapısı

```
engine/
  config.py                  merkezî yapılandırma (URL, timeout, eşikler)
  logging_setup.py           merkezî loglama
  search_engine.py           orkestrasyon, teşhis, önbellek
  server.py  cli.py          REST API ve komut satırı
  fetchers/                  18 veri toplayıcı + BaseFetcher sözleşmesi
  nlp/                       rekonstrüksiyon, hizalama, A-HVP, alıntı keşfi
  utils/                     fonotaktik, ortografi, morfoloji, HTTP istemcisi
  db/                        SQLite, graf, CLDF içe/dışa aktarım
  tests/                     332 test (9'u canlı ağ), fixture'lar, test ikizleri
data/
  seed/                      tohum veri (kaynak künyeli JSON)
  books/                     kullanıcı PDF'leri (tam metin taranır)
web/index.html               tek dosyalık statik panel
scripts/                     fixture kaydedici, veritabanı temizliği
```

## Bilinen sınırlar

- **Alıntı sınıflandırıcı kural tabanlıdır**, eğitilmiş bir ML modeli değildir.
  Çıktıda `method: "rule_based"` olarak bildirilir. Etiketli Türkçe alıntı veri
  kümesi (WOLD ingest'i) tamamlanmadan model eğitimi planlanmamıştır.
- **Semantik aşama** yalnızca `[semantic]` ekstrası kuruluysa kanıt üretir.
- **Neo4j entegrasyonu yoktur.** `db/graph_database.py` Neo4j *şemasına uygun*
  düğüm/kenar yapısı üretir ama Cytoscape.js JSON'u olarak dışa verir.
- **Web paneli tek dosyalık statik HTML'dir**, Next.js kullanılmaz.
- Tohum veri yalnızca 59 kelimeyi kapsar; bu kelimelerin dışında sonuç
  tamamen canlı kaynaklara bağlıdır.

## Lisans

MIT — bkz. [LICENSE](LICENSE).
# etymology
