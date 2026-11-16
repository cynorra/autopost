# autopost

CYNORAPHONK için günlük otomatik TikTok paylaşımı. Her gün 18:47'de (İstanbul) GitHub Actions şunları yapar:

1. `catalog.json` içinden sıradaki şarkıyı seçer (hepsi paylaşılınca en eskiyi yeni bir kesitle tekrar kullanır).
2. Şarkının en yüksek enerjili 30 saniyesini bulur, 1080x1920 dikey klibe çevirir (`ffmpeg`).
3. TikTok Content Posting API ile yayınlar.
4. `state/posted.json` dosyasına kaydeder (aynı kesit tekrarlanmaz).

## Kurulum (bir kez)

### 1. Şarkıları ekle
`catalog.json` içine her şarkı için bir kayıt yaz. İki kaynak türü var:

```json
{ "id": "sarki-adi", "title": "ŞARKI ADI", "file": "media/sarki-adi.mp4" }
{ "id": "baska",     "title": "BAŞKA ŞARKI", "youtube": "https://www.youtube.com/watch?v=..." }
```

- **`file` (önerilen):** Orijinal video veya ses dosyasını (`mp4`, `wav`, `mp3`) `media/` altına koy. Dosya başına 100 MB sınırı var. Yalnızca ses dosyalarında dalga formu görseli üretilir.
- **`youtube`:** `yt-dlp` ile indirilir. GitHub sunucularında YouTube bazen "bot doğrulaması" ister ve indirme başarısız olur, bu durumda `file` kullan.
- İsteğe bağlı `hashtags` alanı (liste) varsayılan etiketleri değiştirir.

### 2. TikTok geliştirici uygulaması
1. https://developers.tiktok.com adresinde giriş yap, bir uygulama oluştur.
2. **Content Posting API** ürününü ekle ve **Direct Post**'u aç. Scope olarak `video.publish` ve `user.info.basic` seçilir.
3. Redirect URI olarak sahip olduğun bir adres kaydet (örn. `https://cynorra.github.io/autopost/callback`; yönlendirme sonrası adres çubuğundaki `code=` değerini kopyalaman yeterli, sayfanın içeriği önemli değil).
4. CYNORAPHONK hesabını uygulamanın **Target Users / sandbox** listesine ekle.
5. Yerelde token al:
   ```bash
   export TIKTOK_CLIENT_KEY=... TIKTOK_CLIENT_SECRET=... TIKTOK_REDIRECT_URI=...
   python -m autopost.tiktok
   ```

### 3. GitHub ayarları (repo → Settings → Secrets and variables → Actions)
| Tür | Ad | Değer |
|---|---|---|
| Secret | `TIKTOK_CLIENT_KEY` | Uygulama anahtarı |
| Secret | `TIKTOK_CLIENT_SECRET` | Uygulama gizli anahtarı |
| Secret | `TIKTOK_REFRESH_TOKEN` | Adım 2.5'ten gelen refresh token |
| Secret (isteğe bağlı) | `SECRETS_PAT` | `secrets` yazma izinli kişisel erişim anahtarı; refresh token değişirse otomatik günceller |
| Variable | `TIKTOK_PRIVACY` | `SELF_ONLY` (başlangıç) → denetimden sonra `PUBLIC_TO_EVERYONE` |

## Önemli: TikTok denetimi
Denetimden (audit) geçmemiş uygulamalar yalnızca **özel (`SELF_ONLY`)** paylaşım yapabilir. Herkese açık yayın için TikTok'a uygulama denetimi başvurusu yapılmalıdır (süre değişebilir, haftalar sürebilir). Hesabın izin verdiği seçenekleri kod her çalışmada sorgular ve izin verilmeyen bir görünürlük istenirse açık bir hata ile durur.

## Deneme
Actions → *Daily TikTok post* → *Run workflow*: varsayılan `dry_run` açıktır, klibi üretir ama göndermez. Üretilen klip, çalışmanın *Artifacts* bölümünden indirilebilir. Gerçek gönderim için `dry_run` kutusunu kapat.

## Yerelde test
```bash
python -m unittest discover -s tests -v
python -m autopost.run --dry-run
```
Gereksinim: `ffmpeg`, `ffprobe`, Python 3.10+.
