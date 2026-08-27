# Yerel PDF Türkoloji Kitaplığı

Bu dizine koyduğunuz `.pdf` dosyaları arama sırasında **tam metin** taranır.

- Metin çıkarımı `pdfminer.six` ile yapılır: `pip install -e ".[pdf]"`
- Çıkarılan metin `.text_cache/` altında önbelleklenir; PDF değişirse yenilenir
- Dizin boşsa kaynak sessizce boş döner (uydurma sonuç üretmez)

Alt dizinler de taranır (`**/*.pdf`).
