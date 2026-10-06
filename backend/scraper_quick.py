"""
Hızlı test: Tüm fonların kategori ve getiri bilgilerini çek (fiyat çekme yok)
"""
import requests
import re
import json
import yfinance as yf

def fetch_all_tefas_funds():
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    all_funds = []
    seen_codes = set()
    
    fund_types = ['YAT', 'EMK', 'BYF']
    
    for ftype in fund_types:
        url = f'https://www.tefas.gov.tr/tr/fon-getirileri?fundType={ftype}'
        print(f"Cekiliyor: {ftype}...")
        
        try:
            r = requests.get(url, headers=headers, timeout=30)
            body = r.text
            
            scripts = re.findall(r'<script[^>]*>(.*?)</script>', body, re.DOTALL)
            big_script = ''
            for s in scripts:
                if len(s) > 50000:
                    big_script = s
                    break
            
            if not big_script:
                continue
            
            decoded = big_script.replace('\\"', '"').replace('\\n', '\n')
            
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
                
                def parse_val(v):
                    if v == 'null': return None
                    try: return round(float(v), 4)
                    except: return None
                
                tur = m[2]
                category = determine_category(tur, m[1])
                
                fund = {
                    "code": code,
                    "name": m[1],
                    "fundType": ftype,
                    "subType": tur,
                    "category": category,
                    "isActive": m[3] == 'true',
                    "price": None,
                    "change": parse_val(m[4]),  # 1 Aylik getiriyi change olarak kullan (fiyat yoksa)
                    "isPositive": (parse_val(m[4]) or 0) >= 0,
                    "getiri1a": parse_val(m[4]),
                    "getiri3a": parse_val(m[5]),
                    "getiri6a": parse_val(m[6]),
                    "getiri1y": parse_val(m[7]),
                    "getiriyb": parse_val(m[8]),
                    "getiri3y": parse_val(m[9]),
                    "getiri5y": parse_val(m[10]),
                    "riskDegeri": int(m[12]) if m[12] else None,
                    "type": "TEFAS",
                    "currency": "TRY"
                }
                
                all_funds.append(fund)
                count += 1
            
            print(f"  {ftype}: {count} fon")
            
        except Exception as e:
            print(f"  HATA: {e}")
    
    return all_funds


def determine_category(sub_type, name):
    s = (sub_type or '').lower()
    n = (name or '').lower()
    
    if 'para p' in s:
        return 'Para Piyasası'
    elif 'hisse' in s or 'hisse' in n:
        return 'Hisse Senedi'
    elif 'borsa yat' in s:
        return 'Borsa Yatırım Fonu (ETF)'
    elif 'tahvil' in s or 'bono' in s:
        return 'Tahvil & Bono'
    elif 'fon sepet' in s:
        return 'Fon Sepeti'
    elif 'serbest' in s:
        return 'Serbest Fon'
    elif 'de' in s and 'ken' in s:
        return 'Karma & Değişken'
    elif 'katil' in s:
        return 'Katılım Fonu'
    elif 'eurobond' in n or 'euro' in n:
        return 'Eurobond'
    elif 'alt' in n and ('n' in s):
        return 'Altın & Kıymetli Maden'
    elif 'emeklilik' in s:
        return 'Emeklilik Fonu'
    elif 'karma' in s:
        return 'Karma & Değişken'
    else:
        return 'Diğer'


# ABD ETF
US_ETFS = ['SPY', 'QQQ', 'VTI', 'IVV', 'VOO', 'ARKK', 'DIA', 'IWM']

def fetch_us_etfs():
    results = []
    for ticker in US_ETFS:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) >= 2:
                prev = float(hist['Close'].iloc[0])
                curr = float(hist['Close'].iloc[-1])
                ch = ((curr - prev) / prev) * 100
            elif len(hist) == 1:
                curr = float(hist['Close'].iloc[-1])
                ch = 0.0
            else:
                continue
                
            info = stock.info
            name = info.get('shortName', ticker)
            
            results.append({
                "code": ticker,
                "name": name,
                "price": round(curr, 2),
                "change": round(ch, 2),
                "isPositive": bool(ch >= 0),
                "type": "ABD_ETF",
                "category": "ABD Borsa Yatırım Fonu",
                "currency": "USD"
            })
            print(f"  {ticker}: ${curr:.2f}")
        except Exception as e:
            print(f"  Hata ({ticker}): {e}")
    return results


if __name__ == "__main__":
    print("Tum fonlar cekiliyor...")
    tefas = fetch_all_tefas_funds()
    
    cat_count = {}
    for f in tefas:
        c = f.get('category', 'Diger')
        cat_count[c] = cat_count.get(c, 0) + 1
    
    print(f"\nToplam TEFAS: {len(tefas)}")
    print("Kategoriler:")
    for c, n in sorted(cat_count.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n}")
    
    print("\nABD ETF cekiliyor...")
    etfs = fetch_us_etfs()
    
    all_data = tefas + etfs
    
    with open('funds.json', 'w', encoding='utf-8') as fp:
        json.dump(all_data, fp, ensure_ascii=False, indent=2)
    
    print(f"\nToplam {len(all_data)} fon funds.json'a kaydedildi!")
