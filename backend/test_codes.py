import requests
import re

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
r = requests.get('https://www.tefas.gov.tr/tr/fon-getirileri?fundType=YAT', headers=headers, timeout=15)
body = r.text

scripts = re.findall(r'<script[^>]*>(.*?)</script>', body, re.DOTALL)
big_script = ''
for s in scripts:
    if len(s) > 100000:
        big_script = s
        break

decoded = big_script.replace('\\"', '"').replace('\\n', '\n')

# fonKodu ilk bulundugu yerin 500 karakter sonrasina bakalim
idx = decoded.find('"fonKodu":"AAL"')
if idx >= 0:
    print("AAL etrafindaki veri:")
    print(decoded[idx:idx+800])
    print("\n---\n")

# Alternatif: Fon kodunun etrafindaki yapiyi anlamak icin
idx2 = decoded.find('"fonKodu":"MAC"')
if idx2 >= 0:
    print("MAC etrafindaki veri:")
    print(decoded[idx2:idx2+800])
else:
    print("MAC bulunamadi, farkli format olabilir")
    # MAC'i body icinde ara
    idx3 = decoded.find('"MAC"')
    if idx3 >= 0:
        print(f"MAC bulundu idx={idx3}:")
        print(decoded[max(0,idx3-200):idx3+200])
