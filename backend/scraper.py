"""
TEFAS + ABD ETF Veri Çekme Botu
GitHub Actions ile her akşam otomatik çalışır.
Tüm TEFAS fonlarını ve popüler ABD ETF'lerini tek bir funds.json dosyasında toplar.
"""
import requests
import re
import json
import yfinance as yf

# ------------------------------------------------------------------
# 1. TEFAS'taki TÜM fonları çek (Fon Getirileri sayfasının RSC payload'undan)
# ------------------------------------------------------------------
def fetch_all_tefas_funds():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    all_funds = []
    seen_codes = set()
    
    # YAT: Yatırım Fonları, EMK: Emeklilik Fonları, BYF: Borsa Yatırım Fonları
    fund_types = ['YAT', 'EMK', 'BYF']
    
    for ftype in fund_types:
        url = f'https://www.tefas.gov.tr/tr/fon-getirileri?fundType={ftype}'
        print(f"\n--- {ftype} fonları çekiliyor: {url}")
        
        try:
            r = requests.get(url, headers=headers, timeout=30)
            body = r.text
            
            # En büyük script bloğunu bul (fon verisi buradadır)
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', body, re.DOTALL)
            big_script = ''
            for s in scripts:
                if len(s) > 50000:
                    big_script = s
                    break
            
            if not big_script:
                print(f"  UYARI: {ftype} için veri bulunamadı!")
                continue
            
            # Escaped JSON'u decode et
            decoded = big_script.replace('\\"', '"').replace('\\n', '\n')
            
            # Her bir fon objesini parse et
            # Format: {"fonKodu":"XXX","fonUnvan":"YYY","fonTurAciklama":"ZZZ",...}
            pattern = r'\{"fonKodu":"([A-Z0-9]{2,5})","fonUnvan":"([^"]+)","fonTurAciklama":"([^"]+)","tefasDurum":(true|false),"getiri1a":([-\d.]+|null),"getiri3a":([-\d.]+|null),"getiri6a":([-\d.]+|null),"getiri1y":([-\d.]+|null),"getiriyb":([-\d.]+|null),"getiri3y":([-\d.]+|null),"getiri5y":([-\d.]+|null),"getiriOrani":([-\d.]+|null),"riskDegeri":"?(\d+)"?\}'
            
            matches = re.findall(pattern, decoded)
            
            count = 0
            for m in matches:
                code = m[0]
                if m[3] != 'true':
                    continue
                if code in seen_codes:
                    continue
                seen_codes.add(code)
                
                # Getiri değerlerini parse et (null ise 0)
                def parse_val(v):
                    if v == 'null':
                        return None
                    try:
                        return round(float(v), 4)
                    except:
                        return None
                
                # Fon türünden kategori belirle
                tur = m[2]  # fonTurAciklama
                category = _determine_category(tur, m[1])
                
                fund = {
                    "code": code,
                    "name": m[1],
                    "fundType": ftype,           # YAT, EMK, BYF
                    "subType": tur,              # Hisse Senedi Şemsiye Fonu, Para Piyasası Şemsiye Fonu vs.
                    "category": category,        # Basitleştirilmiş kategori
                    "isActive": m[3] == 'true',
                    "getiri1a": parse_val(m[4]),  # 1 Aylık
                    "getiri3a": parse_val(m[5]),  # 3 Aylık
                    "getiri6a": parse_val(m[6]),  # 6 Aylık
                    "getiri1y": parse_val(m[7]),  # 1 Yıllık
                    "getiriyb": parse_val(m[8]),  # Yılbaşından Bu Yana
                    "getiri3y": parse_val(m[9]),  # 3 Yıllık
                    "getiri5y": parse_val(m[10]), # 5 Yıllık
                    "riskDegeri": int(m[12]) if m[12] else None,
                    "type": "TEFAS",
                    "currency": "TRY"
                }
                
                all_funds.append(fund)
                count += 1
            
            print(f"  {ftype}: {count} fon parse edildi.")
            
        except Exception as e:
            print(f"  HATA ({ftype}): {e}")
    
    return all_funds


def _determine_category(sub_type, name):
    """Fon alt türünden (fonTurAciklama) basitleştirilmiş kategori belirle."""
    sub_lower = sub_type.lower() if sub_type else ''
    name_lower = name.lower() if name else ''
    
    # Encoding bozuklukları nedeniyle hem Türkçe hem bozuk karakter kontrol et
    if 'para piyasa' in sub_lower or 'para p' in sub_lower:
        return 'Para Piyasası'
    elif 'hisse' in sub_lower or 'hisse' in name_lower:
        return 'Hisse Senedi'
    elif 'bor' in sub_lower and ('yat' in sub_lower or 'etf' in sub_lower):
        return 'Borsa Yatırım Fonu (ETF)'
    elif 'tahvil' in sub_lower or 'bono' in sub_lower:
        return 'Tahvil & Bono'
    elif 'alt' in sub_lower and 'n' in sub_lower:
        return 'Altın & Kıymetli Maden'
    elif 'kar' in sub_lower and ('da' in sub_lower or 'pay' in sub_lower):
        return 'Karma & Değişken'
    elif 'fon sepet' in sub_lower:
        return 'Fon Sepeti'
    elif 'serbest' in sub_lower:
        return 'Serbest Fon'
    elif 'katil' in sub_lower or 'kat' in sub_lower and 'l' in sub_lower:
        return 'Katılım Fonu'
    elif 'emeklilik' in sub_lower or 'emtia' in sub_lower:
        return 'Emeklilik Fonu'
    elif 'eurobond' in name_lower or 'euro' in name_lower:
        return 'Eurobond'
    else:
        return 'Diğer'


# ------------------------------------------------------------------
# 2. Her fonun anlık fiyatını da çekelim (TEFAS detay sayfasından)
# ------------------------------------------------------------------
def enrich_with_prices(funds):
    """Her fonun TEFAS detay sayfasından güncel fiyat ve günlük getiri bilgisini çeker."""
    from bs4 import BeautifulSoup
    import time
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    # Çok fazla fon olduğu için sadece aktif olanları ve batch halinde çekelim
    active_funds = [f for f in funds if f.get('isActive', True)]
    
    print(f"\n--- {len(active_funds)} aktif fonun fiyatı çekiliyor...")
    
    success_count = 0
    for i, fund in enumerate(active_funds):
        code = fund['code']
        try:
            url = f'https://www.tefas.gov.tr/FonAnaliz.aspx?FonKod={code}'
            r = requests.get(url, headers=headers, timeout=10)
            
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                
                ps = soup.find_all('p')
                for j in range(len(ps)):
                    if ps[j].get_text(strip=True) == 'Son Fiyat (TL)':
                        for k in range(j+1, min(j+5, len(ps))):
                            text = ps[k].get_text(strip=True)
                            if text and re.match(r'^[\d,.]+$', text):
                                price_str = text.replace('.', '').replace(',', '.')
                                fund['price'] = float(price_str)
                                break
                    
                    text = ps[j].get_text(strip=True)
                    if 'Günlük Getiri' in text:
                        for k in range(j+1, min(j+5, len(ps))):
                            t = ps[k].get_text(strip=True)
                            if '%' in t:
                                change_str = t.replace('%', '').replace('.', '').replace(',', '.').strip()
                                fund['change'] = float(change_str)
                                fund['isPositive'] = fund['change'] >= 0
                                break
                
                if 'price' in fund:
                    success_count += 1
            
            # Her 50 fonda bir ilerleme göster
            if (i + 1) % 50 == 0:
                print(f"  İlerleme: {i+1}/{len(active_funds)} ({success_count} başarılı)")
            
            time.sleep(0.3)  # Sunucuyu yormamak için kısa bekleme
            
        except Exception as e:
            pass  # Sessizce devam et
    
    print(f"  Tamamlandı: {success_count}/{len(active_funds)} fonun fiyatı alındı.")
    return funds


# ------------------------------------------------------------------
# 3. ABD ETF Fonlarını çek
# ------------------------------------------------------------------
US_ETFS = ['SPY', 'QQQ', 'VTI', 'IVV', 'VOO', 'ARKK', 'DIA', 'IWM', 'EFA', 'VWO']

def fetch_us_etfs():
    results = []
    for ticker in US_ETFS:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) >= 2:
                prev_close = float(hist['Close'].iloc[0])
                current_price = float(hist['Close'].iloc[-1])
                change_pct = ((current_price - prev_close) / prev_close) * 100
            elif len(hist) == 1:
                current_price = float(hist['Close'].iloc[-1])
                change_pct = 0.0
            else:
                continue
                
            info = stock.info
            name = info.get('shortName', ticker)
            
            results.append({
                "code": ticker,
                "name": name,
                "price": round(current_price, 2),
                "change": round(change_pct, 2),
                "isPositive": bool(change_pct >= 0),
                "type": "ABD_ETF",
                "category": "ABD Borsa Yatırım Fonu",
                "currency": "USD"
            })
            print(f"  Başarılı: {ticker} - ${current_price:.2f}")
        except Exception as e:
            print(f"  Hata ({ticker}): {e}")
            
    return results


# ------------------------------------------------------------------
# 4. Ana çalıştırma
# ------------------------------------------------------------------
if __name__ == "__main__":
    print("=" * 60)
    print("  TEFAS + ABD ETF Veri Güncelleme Botu")
    print("=" * 60)
    
    # Adım 1: Tüm TEFAS fonlarını getiri bilgileriyle çek
    tefas_funds = fetch_all_tefas_funds()
    print(f"\nToplam TEFAS fonu: {len(tefas_funds)}")
    
    # Kategorilere göre dağılım
    cat_count = {}
    for f in tefas_funds:
        cat = f.get('category', 'Diğer')
        cat_count[cat] = cat_count.get(cat, 0) + 1
    print("\nKategori dağılımı:")
    for cat, count in sorted(cat_count.items(), key=lambda x: -x[1]):
        print(f"  {cat}: {count}")
    
    # Adım 2: Her fonun anlık fiyatını çek (bu uzun sürer - GitHub Actions'ta sorun değil)
    tefas_funds = enrich_with_prices(tefas_funds)
    
    # Adım 3: ABD ETF'lerini çek
    print("\n--- ABD ETF'leri çekiliyor...")
    etf_funds = fetch_us_etfs()
    
    # Adım 4: Birleştir ve kaydet
    all_funds = tefas_funds + etf_funds
    
    # Fiyatı olmayan fonları da dahil et ama flagle
    for f in all_funds:
        if 'price' not in f:
            f['price'] = None
        if 'change' not in f:
            f['change'] = None
        if 'isPositive' not in f:
            f['isPositive'] = True
    
    with open('funds.json', 'w', encoding='utf-8') as fp:
        json.dump(all_funds, fp, ensure_ascii=False, indent=2)
    
    print(f"\n{'=' * 60}")
    print(f"  Toplam: {len(all_funds)} fon funds.json'a kaydedildi!")
    print(f"  TEFAS: {len(tefas_funds)} | ABD ETF: {len(etf_funds)}")
    print(f"{'=' * 60}")
