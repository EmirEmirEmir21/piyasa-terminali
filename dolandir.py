import html
import json
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

import streamlit as st
import ccxt
import yfinance as yf
import pandas as pd
import plotly.graph_objs as go

# ==============================================================================
# SAYFA YAPILANDIRMASI & DOSYA YOLLARI
# ==============================================================================
st.set_page_config(page_title="Piyasa Vitrin & Takip Terminali", page_icon="💎", layout="wide")

KULLANICI_DOSYASI = Path(__file__).with_name("kullanicilar.json")
TAKIP_DOSYASI = Path(__file__).with_name("takip_listesi.json")
VARSAYILAN_TAKIP = ["BTC-USD", "ETH-USD", "THYAO.IS", "ASELS.IS", "AAPL", "NVDA", "TRY=X", "GC=F"]

# ==============================================================================
# VERİTABANI VE E-POSTA FONKSİYONLARI
# ==============================================================================
def kullanici_yukle():
    try:
        with open(KULLANICI_DOSYASI, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def kullanici_kaydet(veritabani):
    try:
        with open(KULLANICI_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(veritabani, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.error(f"Kullanıcı verisi kaydedilemedi: {e}")

def mail_gonder(alici_mail, varlik, guncel_fiyat, hedef_fiyat):
    # Kendi mail adresinizi ve 16 haneli uygulama şifrenizi buraya girin
    gonderici_mail = st.secrets["MAIL_ADRESI"]  
    sifre = st.secrets["UYGULAMA_SIFRESI"] 
    
    try:
        msg = MIMEMultipart()
        msg['From'] = gonderici_mail
        msg['To'] = alici_mail
        msg['Subject'] = f"🚨 Fiyat Alarmı: {varlik} Hedefe Ulaştı!"
        
        govde = (f"Merhaba,\n\n"
                 f"Takip ettiğiniz {varlik} varlığı belirlediğiniz {hedef_fiyat} seviyesine ulaşmıştır.\n"
                 f"Güncel Fiyat: {guncel_fiyat}\n\n"
                 f"Piyasa Terminali")
        msg.attach(MIMEText(govde, 'plain', 'utf-8'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(gonderici_mail, sifre)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Mail gönderim hatası: {e}")
        return False

# ==============================================================================
# KULLANICI GİRİŞ & KAYIT ARAYÜZÜ (GİRİŞ DUVARI)
# ==============================================================================
if "aktif_kullanici" not in st.session_state:
    st.session_state.aktif_kullanici = None
    st.session_state.alarmlar = {} 

if st.session_state.aktif_kullanici is None:
    st.title("🔐 Sisteme Giriş Yapın")
    st.markdown("Piyasa verilerine, takip listelerinize ve fiyat alarmlarınıza erişmek için giriş yapın.")
    
    tab1, tab2 = st.tabs(["Giriş Yap", "Yeni Kayıt"])
    
    with tab1:
        # clear_on_submit=False ile yanlış tıklamalarda yazdıklarının silinmesini engelliyoruz
        with st.form("giris_formu", clear_on_submit=False):
            # autocomplete="email" sayesinde tarayıcı emir... yazdığında devamını kendi önerir
            giris_mail = st.text_input("E-posta Adresi", key="g_mail", autocomplete="email")
            giris_sifre = st.text_input("Şifre", type="password", key="g_sifre", autocomplete="current-password")
            
            if st.form_submit_button("Giriş Yap"):
                if giris_mail and giris_sifre:
                    kullanicilar = kullanici_yukle()
                    if giris_mail in kullanicilar and kullanicilar[giris_mail] == giris_sifre:
                        st.session_state.aktif_kullanici = giris_mail
                        st.rerun()
                    else:
                        st.error("⚠️ E-posta adresi veya şifre hatalı!")
                else:
                    st.error("Lütfen e-posta ve şifrenizi eksiksiz girin.")
                    
    with tab2:
        with st.form("kayit_formu", clear_on_submit=True):
            kayit_mail = st.text_input("E-posta Adresi", key="k_mail", autocomplete="email")
            kayit_sifre = st.text_input("Şifre", type="password", key="k_sifre", autocomplete="new-password")
            
            if st.form_submit_button("Kayıt Ol"):
                if kayit_mail and kayit_sifre:
                    kullanicilar = kullanici_yukle()
                    if kayit_mail in kullanicilar:
                        st.error("⚠️ Bu e-posta adresi zaten sistemde kayıtlı!")
                    else:
                        kullanicilar[kayit_mail] = kayit_sifre
                        kullanici_kaydet(kullanicilar)
                        st.success("✅ Kayıt başarılı! Lütfen 'Giriş Yap' sekmesine geçerek sisteme girin.")
                else:
                    st.error("Lütfen tüm alanları doldurun.")
    
    st.stop() # Kullanıcı giriş yapana kadar alt kısımları çalıştırma

# ==============================================================================
# SİSTEM İÇİ AYARLAR & YARDIMCI FONKSİYONLAR
# ==============================================================================
def takip_yukle():
    try:
        with open(TAKIP_DOSYASI, "r", encoding="utf-8") as f:
            veri = json.load(f)
            if isinstance(veri, list): return veri
    except Exception:
        pass
    return VARSAYILAN_TAKIP.copy()

def takip_kaydet(liste):
    try:
        with open(TAKIP_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(liste, f, ensure_ascii=False, indent=2)
    except Exception as e:
        st.warning(f"Takip listesi dosyaya kaydedilemedi: {e}")

if "takip_secim" not in st.session_state:
    st.session_state.takip_secim = takip_yukle()
    st.session_state.takip_son_kaydedilen = list(st.session_state.takip_secim)

st.sidebar.title("📌 Ana Menü")
menu = st.sidebar.radio(
    "Bölüm Seçin:",
    ["🏠 Ana Sayfa (Piyasa Vitrini)", "🔥 Kripto Borsası (Binance Canlı)", "🏛️ Borsa İstanbul (BIST)", "🌎 ABD Borsaları & Emtia"]
)
oto_yenile = False

def mini_grafik_ciz(seri, renk, baslik, birim):
    min_deger = float(seri.min())
    max_deger = float(seri.max())
    esneklik = (max_deger - min_deger) * 0.1 if max_deger != min_deger else min_deger * 0.05
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=seri.index, y=seri.values, mode="lines", fill="tozeroy", line=dict(color=renk, width=2.5), name=baslik))
    fig.update_layout(title=dict(text=f"Son 6 Aylık Trend ({birim})", font=dict(size=13)), margin=dict(l=10, r=10, t=30, b=10), height=200, xaxis=dict(visible=True, tickformat="%b %Y"), yaxis=dict(side="right", range=[min_deger - esneklik, max_deger + esneklik], tickformat=",.2f" if seri.iloc[-1] < 1000 else ",.0f"), showlegend=False)
    return fig

@st.cache_data(ttl=60)
def kapak_verilerini_getir():
    df = yf.download(["BTC-USD", "GC=F", "TRY=X"], period="6mo", interval="1d", progress=False)
    kapanis = df["Close"].ffill().dropna()
    kapanis["GRAM_ALTIN"] = (kapanis["GC=F"] * kapanis["TRY=X"]) / 31.1034768
    return kapanis

@st.cache_data(ttl=30, show_spinner=False)
def takip_verilerini_getir(semboller: tuple):
    satirlar, bulunamayan = [], []
    try:
        df = yf.download(list(semboller), period="5d", interval="1d", progress=False)
        if df is None or df.empty: return [], list(semboller)
        kapanislar = df["Close"] if "Close" in df else df
        if isinstance(kapanislar, pd.Series): kapanislar = kapanislar.to_frame(name=semboller[0])
    except Exception: return [], list(semboller)

    for sembol in semboller:
        try:
            if sembol not in kapanislar.columns:
                bulunamayan.append(sembol)
                continue
            seri = kapanislar[sembol].dropna()
            if len(seri) < 2:
                bulunamayan.append(sembol)
                continue
            son_fiyat = float(seri.iloc[-1])
            onceki_fiyat = float(seri.iloc[-2])
            fark = son_fiyat - onceki_fiyat
            yuzde = (fark / onceki_fiyat) * 100 if onceki_fiyat != 0 else 0.0
            satirlar.append({"Varlık / Sembol": sembol, "Güncel Değer": son_fiyat, "Değişim (Tutar)": fark, "Değişim Oranı (%)": yuzde})
        except Exception:
            bulunamayan.append(sembol)
    return satirlar, bulunamayan

KATALOG = {
    "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana", "BNB-USD": "BNB", "XRP-USD": "XRP", "DOGE-USD": "Dogecoin",
    "TRY=X": "Dolar/TL", "EURTRY=X": "Euro/TL", "GC=F": "Ons Altın", "SI=F": "Ons Gümüş", "BZ=F": "Brent Petrol",
    "XU100.IS": "BIST 100", "THYAO.IS": "THY", "ASELS.IS": "ASELSAN", "TUPRS.IS": "TÜPRAŞ", "KCHOL.IS": "Koç Holding", "GARAN.IS": "Garanti BBVA",
    "AAPL": "Apple", "NVDA": "NVIDIA", "MSFT": "Microsoft", "TSLA": "Tesla"
}

def _sayi_bicimle(v): return f"{v:,.4f}" if abs(v) < 10 else f"{v:,.2f}"

def ozel_sembol_ekle(onayli_sembol):
    if onayli_sembol and onayli_sembol not in st.session_state.takip_secim:
        st.session_state.takip_secim.append(onayli_sembol)
        takip_kaydet(st.session_state.takip_secim)
        st.session_state.takip_son_kaydedilen = list(st.session_state.takip_secim)
        if "takip_ozel_input" in st.session_state: st.session_state.takip_ozel_input = ""

# ==============================================================================
# SOL MENÜ: TAKİP VE ALARM PANELİ
# ==============================================================================
def takip_listesi_paneli():
    sb = st.sidebar
    sb.divider()
    
    # Kullanıcı Hesabı & Çıkış Yap
    sb.markdown(f"👤 **Hesap:** `{st.session_state.aktif_kullanici}`")
    if sb.button("Çıkış Yap", use_container_width=True):
        st.session_state.aktif_kullanici = None
        st.rerun()

    sb.divider()
    sb.subheader("📌 Takip Listesi")
    secenekler = list(KATALOG.keys()) + [s for s in st.session_state.takip_secim if s not in KATALOG]

    with sb.expander("➕ Takip edilecekleri seç", expanded=False):
        guncel_secim = st.multiselect("Takip edilecekler:", secenekler, default=st.session_state.takip_secim, key="secim_widget", format_func=lambda s: f"{s} · {KATALOG[s]}" if s in KATALOG else s)
        if guncel_secim != st.session_state.takip_secim:
            st.session_state.takip_secim = guncel_secim
            takip_kaydet(st.session_state.takip_secim)
            st.session_state.takip_son_kaydedilen = list(st.session_state.takip_secim)
            st.rerun()

        aranan_sembol = st.text_input("Listede yok mu? Sembol yazın:", key="takip_ozel_input", placeholder="Örn: EREGL, SOL").strip().upper()
        if aranan_sembol:
            tahmin_is = f"{aranan_sembol}.IS" if aranan_sembol.isalpha() and 4 <= len(aranan_sembol) <= 5 else aranan_sembol
            tahmin_usd = f"{aranan_sembol}-USD" if aranan_sembol.isalpha() else aranan_sembol
            aranacaklar = list(set([aranan_sembol, tahmin_is, tahmin_usd]))
            with st.spinner("Aranıyor..."):
                try:
                    df_onizleme = yf.download(aranacaklar, period="5d", interval="1d", progress=False)
                    bulundu = False
                    if df_onizleme is not None and not df_onizleme.empty:
                        kapanislar = df_onizleme["Close"] if "Close" in df_onizleme else df_onizleme
                        if isinstance(kapanislar, pd.Series): kapanislar = kapanislar.to_frame(name=aranacaklar[0])
                        for s in [tahmin_is, tahmin_usd, aranan_sembol]:
                            if s in kapanislar.columns:
                                seri = kapanislar[s].dropna()
                                if not seri.empty and len(seri) > 0:
                                    try:
                                        son_fiyat = float(seri.iloc[-1])
                                        st.success(f"✅ {s} ➔ {son_fiyat:,.2f}")
                                        if st.button(f"➕ {s} Ekle", use_container_width=True):
                                            ozel_sembol_ekle(s)
                                            st.rerun()
                                        bulundu = True
                                        break
                                    except (ValueError, TypeError): continue
                    if not bulundu: st.error(f"⚠️ Bulunamadı.")
                except Exception: st.error(f"Hata oluştu.")

    secili = list(st.session_state.takip_secim)
    if not secili:
        sb.caption("Henüz takip edilen varlık yok.")
        return

    satirlar, bulunamayan = takip_verilerini_getir(tuple(secili))
    sozluk = {r["Varlık / Sembol"]: r for r in satirlar}

    parcalar = []
    for sembol in secili:
        ad = html.escape(sembol)
        r = sozluk.get(sembol)
        if r:
            guncel_fiyat = r['Güncel Değer']
            yuzde = r["Değişim Oranı (%)"]
            renk = "#16a34a" if yuzde > 0 else "#dc2626" if yuzde < 0 else "#9ca3af"
            ok = "▲" if yuzde > 0 else "▼" if yuzde < 0 else "■"
            sag = f"{_sayi_bicimle(guncel_fiyat)}<br><span style='color:{renk};font-size:0.72rem;'>{ok} {yuzde:+.2f}%</span>"
            
            # Arka planda Alarm Kontrolü (Giriş Yapılan Maile Atar)
            if sembol in st.session_state.alarmlar:
                alarm = st.session_state.alarmlar[sembol]
                if not alarm["tetiklendi"]:
                    tetikle = False
                    if alarm["yon"] == ">=" and guncel_fiyat >= alarm["hedef"]: tetikle = True
                    elif alarm["yon"] == "<=" and guncel_fiyat <= alarm["hedef"]: tetikle = True
                    
                    if tetikle:
                        basari = mail_gonder(st.session_state.aktif_kullanici, sembol, guncel_fiyat, alarm["hedef"])
                        if basari:
                            st.toast(f"📧 {sembol} hedefine ulaştı, bilgilendirme maili gönderildi!")
                            alarm["tetiklendi"] = True
        else:
            sag = "<span style='color:#9ca3af;'>veri yok</span>"

        parcalar.append(f"<div style='display:flex;justify-content:space-between;align-items:center;font-size:0.8rem;padding:4px 2px;border-bottom:1px solid rgba(128,128,128,0.25);'><span style='font-weight:600;'>{ad}</span><span style='text-align:right;'>{sag}</span></div>")

    sb.markdown("".join(parcalar), unsafe_allow_html=True)
    if sb.button("🔄 Yenile", key="takip_yenile", use_container_width=True):
        takip_verilerini_getir.clear()
        st.rerun()

    # E-posta Alarm Arayüzü
    sb.divider()
    sb.subheader("🔔 E-Posta Fiyat Alarmı")
    alarm_varlik = sb.selectbox("Varlık Seçin:", secili)
    alarm_hedef = sb.number_input("Hedef Fiyat", min_value=0.0, format="%.4f")
    alarm_yon = sb.radio("Yön:", ["Belirtilen Fiyatı Geçerse (>=)", "Belirtilen Fiyata Düşerse (<=)"])
    
    if sb.button("Alarmı Aktifleştir", use_container_width=True):
        st.session_state.alarmlar[alarm_varlik] = {
            "hedef": alarm_hedef, 
            "yon": ">=" if "Geçerse" in alarm_yon else "<=", 
            "tetiklendi": False
        }
        sb.success(f"{alarm_varlik} için alarm kuruldu!")

# ==============================================================================
# MODÜLLER: ANA SAYFA & PİYASA EKRANLARI
# ==============================================================================
if menu == "🏠 Ana Sayfa (Piyasa Vitrini)":
    st.title("💎 Piyasa Özeti: Kripto, Altın ve Döviz")
    st.markdown("Anlık **Bitcoin**, **Gram Altın** ve **Dolar/TL** piyasa göstergeleri.")

    ust_col1, ust_col2 = st.columns([4, 1])
    with ust_col2:
        if st.button("🔄 Verileri Yenile", use_container_width=True): st.cache_data.clear()

    st.divider()

    with st.spinner("Güncel piyasa kurları yükleniyor..."):
        kapanis_df = kapak_verilerini_getir()

        try:
            borsa = ccxt.binance({'enableRateLimit': True})
            btc_ticker = borsa.fetch_ticker("BTC/USDT")
            btc_fiyat = float(btc_ticker["last"])
            btc_degisim = float(btc_ticker["change"])
            btc_yuzde = float(btc_ticker["percentage"])
        except Exception:
            btc_fiyat = float(kapanis_df["BTC-USD"].iloc[-1])
            btc_onceki = float(kapanis_df["BTC-USD"].iloc[-2])
            btc_degisim = btc_fiyat - btc_onceki
            btc_yuzde = (btc_degisim / btc_onceki) * 100

        usd_fiyat = float(kapanis_df["TRY=X"].iloc[-1])
        usd_degisim = usd_fiyat - float(kapanis_df["TRY=X"].iloc[-2])
        usd_yuzde = (usd_degisim / float(kapanis_df["TRY=X"].iloc[-2])) * 100

        gram_fiyat = float(kapanis_df["GRAM_ALTIN"].iloc[-1])
        gram_degisim = gram_fiyat - float(kapanis_df["GRAM_ALTIN"].iloc[-2])
        gram_yuzde = (gram_degisim / float(kapanis_df["GRAM_ALTIN"].iloc[-2])) * 100

        col_btc, col_altin, col_dolar = st.columns(3)

        with col_btc:
            with st.container(border=True):
                st.subheader("₿ Bitcoin (BTC)")
                st.metric("Anlık Fiyat (USDT)", f"${btc_fiyat:,.2f}", f"{btc_degisim:+,.2f} $ ({btc_yuzde:+.2f}%)")
                st.caption(f"🇹🇷 TL Karşılığı: **₺{(btc_fiyat * usd_fiyat):,.0f}**")
                st.plotly_chart(mini_grafik_ciz(kapanis_df["BTC-USD"], "#F7931A", "BTC", "USD"), use_container_width=True)

        with col_altin:
            with st.container(border=True):
                st.subheader("🪙 Gram Altın")
                st.metric("Spot Gram Altın (TL)", f"₺{gram_fiyat:,.2f}", f"{gram_degisim:+,.2f} ₺ ({gram_yuzde:+.2f}%)")
                st.caption(f"🌎 Ons Altın: **${float(kapanis_df['GC=F'].iloc[-1]):,.2f}**")
                st.plotly_chart(mini_grafik_ciz(kapanis_df["GRAM_ALTIN"], "#FFD700", "Gram Altın", "TL"), use_container_width=True)

        with col_dolar:
            with st.container(border=True):
                st.subheader("💵 Dolar / TL")
                st.metric("USD / TRY Kuru", f"₺{usd_fiyat:,.4f}", f"{usd_degisim:+,.4f} ₺ ({usd_yuzde:+.2f}%)")
                st.caption(f"💶 100 Dolar: **₺{(usd_fiyat * 100):,.2f}**")
                st.plotly_chart(mini_grafik_ciz(kapanis_df["TRY=X"], "#2ECC71", "USD/TRY", "TL"), use_container_width=True)

elif menu == "🔥 Kripto Borsası (Binance Canlı)":
    st.title("🔥 Canlı Binance Kripto Terminali")
    borsa = ccxt.binance({'enableRateLimit': True})
    populer_coinler = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "AVAX/USDT", "DOGE/USDT"]
    
    secilen_cift = st.sidebar.selectbox("Kripto Çifti Seçin:", populer_coinler)
    ozel_cift = st.sidebar.text_input("Veya Özel Çift:").strip().upper()
    aktif_cift = ozel_cift if ozel_cift else secilen_cift
    zaman_dilimi = st.sidebar.selectbox("Mum Zaman Dilimi:", ["1m", "5m", "15m", "1h", "4h", "1d"], index=2)
    oto_yenile = st.sidebar.checkbox("⚡ Saniyelik Otomatik Yenileme (5 sn)")

    try:
        ticker = borsa.fetch_ticker(aktif_cift)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"Binance: {aktif_cift}", f"{ticker['last']:,.2f} USDT", f"{ticker['percentage']:+.2f}%")
        col2.metric("24s En Yüksek", f"{ticker['high']:,.2f} USDT")
        col3.metric("24s En Düşük", f"{ticker['low']:,.2f} USDT")
        col4.metric("24s Hacim", f"{ticker['quoteVolume']:,.0f} $")

        ohlcv = borsa.fetch_ohlcv(aktif_cift, timeframe=zaman_dilimi, limit=100)
        df_kripto = pd.DataFrame(ohlcv, columns=['Tarih', 'Open', 'High', 'Low', 'Close', 'Volume'])
        df_kripto['Tarih'] = pd.to_datetime(df_kripto['Tarih'], unit='ms')
        
        fig = go.Figure(data=[go.Candlestick(x=df_kripto['Tarih'], open=df_kripto['Open'], high=df_kripto['High'], low=df_kripto['Low'], close=df_kripto['Close'], name=aktif_cift)])
        fig.update_layout(title=f"{aktif_cift} Canlı Mum Grafiği", xaxis_rangeslider_visible=False, height=480)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e: st.error(f"Veri çekilemedi: {e}")

else:
    st.title(menu)
    hisse_havuzu = {
        "🏛️ Borsa İstanbul (BIST)": {"BIST 100": "XU100.IS", "THY": "THYAO.IS", "ASELSAN": "ASELS.IS", "TÜPRAŞ": "TUPRS.IS"},
        "🌎 ABD Borsaları & Emtia": {"Apple": "AAPL", "NVIDIA": "NVDA", "Tesla": "TSLA", "Ons Altın": "GC=F"}
    }
    
    secilen_varlik = st.sidebar.selectbox("Varlık Seçin:", list(hisse_havuzu[menu].keys()))
    ozel_kod = st.sidebar.text_input("Veya Özel Sembol:").strip().upper()
    aktif_kod = ozel_kod if ozel_kod else hisse_havuzu[menu][secilen_varlik]
    periyot = st.sidebar.selectbox("Zaman Aralığı:", ["1mo", "3mo", "6mo", "1y"], index=2)

    df = yf.download(aktif_kod, period=periyot, interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)

    if not df.empty:
        son = float(df["Close"].iloc[-1])
        onceki = float(df["Close"].iloc[-2]) if len(df) > 1 else son
        yuzde = ((son - onceki) / onceki) * 100 if onceki != 0 else 0

        c1, c2, c3 = st.columns(3)
        c1.metric(f"{aktif_kod}", f"{son:,.2f}", f"{son - onceki:+,.2f} ({yuzde:+.2f}%)")
        c2.metric(f"En Yüksek", f"{float(df['High'].max()):,.2f}")
        c3.metric(f"En Düşük", f"{float(df['Low'].min()):,.2f}")

        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name=aktif_kod)])
        fig.update_layout(title=f"{aktif_kod} Fiyat Grafiği", xaxis_rangeslider_visible=False, height=480)
        st.plotly_chart(fig, use_container_width=True)

# ÇAĞRILAR
takip_listesi_paneli()
if oto_yenile and menu == "🔥 Kripto Borsası (Binance Canlı)":
    time.sleep(5)
    st.rerun()
