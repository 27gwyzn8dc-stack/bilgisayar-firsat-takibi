# Ücretsiz bulut kurulum hazırlığı

Henüz buluta kurulmadı. Bu klasörün kendisi depo kökü olmalı.

1. GitHub Free hesabı aç. Kart veya ücretli plan gerekli değil.
2. Kodun herkese açık yayımlanmasına karar verdikten sonra yalnızca kaynak
   dosyalarla public depo oluştur. `.env`, `data`, `.venv`, `durum.html`,
   loglar ve anahtarlar yüklenmez. Özel depolarda ücretsiz dakika kotası vardır.
3. Settings → Secrets and variables → Actions altında `NTFY_TOPIC` ve
   `STATE_KEY` sırlarını ekle. Kanal mevcut yerel `.env` dosyasından taşınır.
   STATE_KEY bir defa `Fernet.generate_key()` ile oluşturulur ve güvenle saklanır;
   her çalışmada değiştirilmez. Sohbete veya kaynak koduna yazılmaz.
4. Actions → Bilgisayar fiyat takibi → Run workflow. İlk çalışmada bootstrap
   işaretlenir. Sonraki çalışmalarda kapalı kalır. Yerel veritabanı ayrıca
   şifrelenerek taşınmazsa bulut geçmişi sıfırdan başlar.
5. İlk bulut taramasını ve iPhone bildirimini doğruladıktan sonra yerel
   `stop.ps1` ile eski çalışanı kapat; iki bağımsız kopya çift bildirim üretebilir.

Planlanan tarama 20 dakikada birdir. GitHub zamanlaması gecikebilir ve public
depolar 60 gün etkinlik yoksa zamanlamayı kapatır. Bu bir kesintisiz VPS değildir.
Kaynak siteler bulut IP adreslerini engelleyebilir; yerel başarı bulut başarısını
garanti etmez. 403 durumunda koruma aşılmadan kaynak atlanır.

SQLite ve kategori sıraları Fernet ile şifrelenir, iki gün tutulan artifact olarak
saklanır. Önceki artifact kaybolursa otomatik boş geçmişle devam edilmez.
Anahtarsız okunamaz; bildirim kanalı bu yedeğe konulmaz. Yükleme hatası veya
işlemin zorla kesilmesi halinde son bildirim kaydı kaybolabilir; GitHub başarısız
çalışma uyarılarını açık tut. GitHub depolama kullanımını izle; ücretsiz hizmet
sınırsız depolama veya erişilebilirlik garantisi değildir.

Fiyat kapsamı: alt/üst TL sınırı yok, varsayılan eşik %15. Bir mağazanın çizili
fiyatı kanıt sayılmaz. İlk gün aynı GTIN için en az üç bağımsız karşı teklif,
en az iki kaynak ve tutarlı fiyatlar gerekir. Diğer ürünlerde tarihsel doğrulama
yeterli örnek biriktikten sonra devreye girer. Kategoriler sırayla taranır;
mağazaların tüm ürünleri ve tüm sayfaları kapsandığı iddia edilmez.
