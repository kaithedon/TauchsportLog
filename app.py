import streamlit as st
import pandas as pd
import numpy as np
import gspread
from gspread_dataframe import set_with_dataframe, get_as_dataframe
import hashlib
import datetime
import uuid
import base64
import io
from PIL import Image
from streamlit_option_menu import option_menu
from tenacity import retry, wait_exponential, stop_after_attempt
import pytz

def get_now_berlin():
    return datetime.datetime.now(pytz.timezone('Europe/Berlin')).replace(tzinfo=None)

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Tauchsportclub - Deep Dive Counter",
    page_icon="favicon.png",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- STYLING ---
st.markdown("""
    <style>
    /* Layout/Padding Fix für Mobilgeräte */
    .block-container {
        padding-left: 0.2rem !important;
        padding-right: 0.2rem !important;
        padding-top: 1.5rem !important;
        padding-bottom: 1.5rem !important;
    }
    
    /* Storno Button Special */
    .storno-btn>button {
        border-color: #ff4b4b !important;
        color: #ff4b4b !important;
    }
    .storno-btn>button:hover {
        background-color: #ff4b4b !important;
        color: white !important;
    }
    
    /* Link styling for PayPal */
    a.paypal-link {
        display: inline-block;
        padding: 10px 20px;
        background-color: #0070ba;
        color: white !important;
        text-decoration: none;
        border-radius: 5px;
        font-weight: bold;
        text-align: center;
        width: 100%;
        margin-top: 10px;
    }
    a.paypal-link:hover {
        background-color: #005ea6;
    }
    </style>
""", unsafe_allow_html=True)

# --- CONSTANTS ---
SHEET_USER_DB = "User_DB"
SHEET_GETRAENKE_DB = "Getraenke_DB"
SHEET_KONSUM_LOG = "Konsum_Log"
SHEET_GLOBALE_STATS = "Globale_Stats"
SHEET_BACKUP_HISTORY = "Backup_History"
SHEET_ACTIVATION_CODES = "Activation_Codes"
SHEET_STORIES = "Stories"

COLUMNS = {
    SHEET_USER_DB: ["Username", "Password_Hash", "Gewicht_kg", "Groesse_cm", "Geschlecht", "Rolle", "Profilbild_Url"],
    SHEET_GETRAENKE_DB: ["Marke", "Sorte", "Alkoholgehalt_Vol", "Standard_Menge_ml", "Barcode"],
    SHEET_KONSUM_LOG: ["Log_ID", "Zeitstempel", "Username", "Marke", "Sorte", "Menge_ml", "Alk_Vol", "latitude", "longitude"],
    SHEET_GLOBALE_STATS: ["Key", "Value"],
    SHEET_BACKUP_HISTORY: ["Backup_Zeitstempel", "Log_ID", "Zeitstempel", "Username", "Marke", "Sorte", "Menge_ml", "Alk_Vol", "latitude", "longitude"],
    SHEET_ACTIVATION_CODES: ["Code", "Used", "Used_By", "Used_At"],
    SHEET_STORIES: ["username", "image_data", "timestamp"]
}

def generate_master_drinks():
    Brauereien = [
        "Licher", "Veltins", "Krombacher", "Bitburger", "Becks", "Warsteiner", "Radeberger", 
        "Jever", "Flensburger", "Rothaus", "Ur-Krostitzer", "König Pilsener", "Hasseröder",
        "Augustiner", "Bayreuther", "Chiemseer", "Tegernseer", "Paulaner", "Spaten", 
        "Oberdorfer", "Büble", "Hacker-Pschorr", "Löwenbräu", "Weihenstephan", "Ayinger",
        "Erdinger", "Franziskaner", "Maisel's", "Schöfferhofer", "Schneider Weisse", "Benediktiner",
        "Früh", "Reissdorf", "Gaffel", "Füchschen", "Uerige", "Diebels",
        "Astra", "Sternburg", "Oettinger", "5,0 Original", "Paderborner",
        "Heineken", "Corona", "Desperados", "Salitos", "Gösser", "San Miguel", "Peroni", 
        "Guinness", "Kilkenny", "Budweiser", "Estrella Damm", "Carlsberg", "Tuborg"
    ]

    Sorten_Konfiguration = [
        {"Sorte": "Pils (0.33l)", "Vol": 4.8, "Menge": 330},
        {"Sorte": "Pils (0.5l)", "Vol": 4.8, "Menge": 500},
        {"Sorte": "Helles (0.5l)", "Vol": 5.0, "Menge": 500},
        {"Sorte": "Export (0.5l)", "Vol": 5.2, "Menge": 500},
        {"Sorte": "Hefe-Weizen (0.5l)", "Vol": 5.5, "Menge": 500},
        {"Sorte": "Kristall-Weizen (0.5l)", "Vol": 5.5, "Menge": 500},
        {"Sorte": "Dunkelbier (0.5l)", "Vol": 5.1, "Menge": 500},
        {"Sorte": "Radler (0.33l)", "Vol": 2.5, "Menge": 330},
        {"Sorte": "Radler (0.5l)", "Vol": 2.5, "Menge": 500},
        {"Sorte": "Alkoholfrei (0.33l)", "Vol": 0.0, "Menge": 330},
        {"Sorte": "Alkoholfrei (0.5l)", "Vol": 0.0, "Menge": 500}
    ]

    Apfelwein_Marken = ["Possmann", "Bembel-with-Care", "Rapp's", "Höhl", "Heil"]
    Apfelwein_Marken.append("Apfelwein (Standard / Hausmarke)")
    
    Apfelwein_Sorten = [
        {"Sorte": "Pur (0.5l)", "Vol": 5.5, "Menge": 500},
        {"Sorte": "Sauergespratzt (0.5l)", "Vol": 4.0, "Menge": 500},
        {"Sorte": "Süßgespratzt (0.5l)", "Vol": 3.5, "Menge": 500},
        {"Sorte": "Cola-Ascher (0.5l)", "Vol": 3.8, "Menge": 500},
        {"Sorte": "Kirsch-Weis (0.5l)", "Vol": 4.2, "Menge": 500}
    ]

    Spirituosen = [
        {"Name": "Bacardi Carta Blanca", "Vol": 37.5, "Menge": 40},
        {"Name": "Bacardi Oakheart", "Vol": 35.0, "Menge": 40},
        {"Name": "Havana Club 3 Jahre", "Vol": 40.0, "Menge": 40},
        {"Name": "Havana Club 7 Jahre", "Vol": 40.0, "Menge": 40},
        {"Name": "Captain Morgan Spiced Gold", "Vol": 35.0, "Menge": 40},
        {"Name": "Jack Daniel's Old No. 7", "Vol": 40.0, "Menge": 40},
        {"Name": "Jack Daniel's Honey", "Vol": 35.0, "Menge": 40},
        {"Name": "Jim Beam Bourbon", "Vol": 40.0, "Menge": 40},
        {"Name": "Johnny Walker Red Label", "Vol": 40.0, "Menge": 40},
        {"Name": "Jameson Irish Whiskey", "Vol": 40.0, "Menge": 40},
        {"Name": "Tullamore Dew", "Vol": 40.0, "Menge": 40},
        {"Name": "Absolut Wodka", "Vol": 40.0, "Menge": 40},
        {"Name": "Wodka Gorbatschow", "Vol": 37.5, "Menge": 40},
        {"Name": "Smirnoff Ice / Wodka", "Vol": 37.5, "Menge": 40},
        {"Name": "Three Sixty Wodka", "Vol": 37.5, "Menge": 40},
        {"Name": "Gordon's London Dry Gin", "Vol": 37.5, "Menge": 40},
        {"Name": "Bombay Sapphire Gin", "Vol": 40.0, "Menge": 40},
        {"Name": "Hendrick's Gin", "Vol": 44.0, "Menge": 40},
        {"Name": "Tanqueray Gin", "Vol": 47.3, "Menge": 40},
        {"Name": "Jägermeister", "Vol": 35.0, "Menge": 40},
        {"Name": "Asbach Uralt", "Vol": 38.0, "Menge": 40},
        {"Name": "Campari", "Vol": 25.0, "Menge": 40},
        {"Name": "Malibu Kokoslikör", "Vol": 21.0, "Menge": 40},
        {"Name": "Aperol", "Vol": 11.0, "Menge": 40},
        {"Name": "Lillet Blanc", "Vol": 17.0, "Menge": 40},
        {"Name": "Ramazzotti", "Vol": 30.0, "Menge": 40},
        {"Name": "Averna", "Vol": 29.0, "Menge": 40},
        {"Name": "Baileys Irish Cream", "Vol": 17.0, "Menge": 40},
        {"Name": "Licor 43", "Vol": 31.0, "Menge": 40},
        {"Name": "Batida de Côco", "Vol": 16.0, "Menge": 40}
    ]

    Filler = [
        {"Name": "mit Coca-Cola", "Menge": 260},
        {"Name": "mit Coca-Cola Zero", "Menge": 260},
        {"Name": "mit Fanta", "Menge": 260},
        {"Name": "mit Sprite", "Menge": 260},
        {"Name": "mit Mezzo Mix", "Menge": 260},
        {"Name": "mit Red Bull Energy", "Menge": 210},
        {"Name": "mit Red Bull Sugarfree", "Menge": 210},
        {"Name": "mit Schweppes Bitter Lemon", "Menge": 210},
        {"Name": "mit Schweppes Tonic Water", "Menge": 210},
        {"Name": "mit Schweppes Ginger Ale", "Menge": 210},
        {"Name": "mit Thomas Henry Tonic", "Menge": 210},
        {"Name": "mit Granini Orangensaft", "Menge": 260},
        {"Name": "mit Granini Maracujasaft", "Menge": 260},
        {"Name": "mit Granini Apfelsaft klar", "Menge": 260},
        {"Name": "mit Schweppes Wild Berry", "Menge": 210},
        {"Name": "mit Club Mate", "Menge": 260},
        {"Name": "mit Sprudelwasser (Skinny Bitch)", "Menge": 260}
    ]

    Shots = [
        {"Marke": "Berliner Luft", "Sorte": "Pfeffi Shot", "Vol": 18.0, "Menge": 20},
        {"Marke": "Berliner Luft", "Sorte": "Pfeffi Doppelshot", "Vol": 18.0, "Menge": 40},
        {"Marke": "Flimm", "Sorte": "Waldmeister Shot", "Vol": 15.0, "Menge": 20},
        {"Marke": "Kleiner Feigling", "Sorte": "Original Klopfer", "Vol": 20.0, "Menge": 20},
        {"Marke": "Kleiner Feigling", "Sorte": "Erdbeer Erdbeere", "Vol": 15.0, "Menge": 20},
        {"Marke": "Sourz", "Sorte": "Apple Shot", "Vol": 15.0, "Menge": 20},
        {"Marke": "Sourz", "Sorte": "Blackcurrant Shot", "Vol": 15.0, "Menge": 20},
        {"Marke": "Ficken", "Sorte": "Johannisbeer-Partyschnaps", "Vol": 15.0, "Menge": 20},
        {"Marke": "Dos Mas", "Sorte": "Mex Shot (Zimt)", "Vol": 15.0, "Menge": 20},
        {"Marke": "Dos Mas", "Sorte": "Pink Shot (Beere)", "Vol": 15.0, "Menge": 20},
        {"Marke": "Sierra Tequila", "Sorte": "Silber Shot", "Vol": 38.0, "Menge": 20},
        {"Marke": "Sierra Tequila", "Sorte": "Gold Shot", "Vol": 38.0, "Menge": 20},
        {"Marke": "Ouzo 12", "Sorte": "Shot", "Vol": 38.0, "Menge": 20},
        {"Marke": "Sambuca Molinari", "Sorte": "Shot", "Vol": 40.0, "Menge": 40},
        {"Marke": "Mexikaner", "Sorte": "Scharfer Tomatenshot (Hausgemacht)", "Vol": 15.0, "Menge": 20},
        {"Marke": "B52", "Sorte": "Schichtshot", "Vol": 28.0, "Menge": 40}
    ]

    drinks = []
    
    for b in Brauereien:
        for s in Sorten_Konfiguration:
            drinks.append([b, s["Sorte"], s["Vol"], s["Menge"]])
            
    for m in Apfelwein_Marken:
        for s in Apfelwein_Sorten:
            drinks.append([m, s["Sorte"], s["Vol"], s["Menge"]])
            
    for sp in Spirituosen:
        for f in Filler:
            gesamtmenge = sp["Menge"] + f["Menge"]
            alk_vol = round((sp["Menge"] * sp["Vol"]) / gesamtmenge, 2)
            sorte_name = f'Longdrink {f["Name"]} ({gesamtmenge}ml)'
            drinks.append([sp["Name"], sorte_name, alk_vol, gesamtmenge])
            
    for s in Shots:
        drinks.append([s["Marke"], s["Sorte"], s["Vol"], s["Menge"]])
        
    return drinks

# --- DATABASE HELPERS ---
@st.cache_resource
def get_gspread_client():
    try:
        # Streamlit secrets dict needs to be converted to a normal dict for gspread
        creds_dict = dict(st.secrets["connections"]["gsheets"])
        
        # If public link without service account is used, this will fail. We need the service account.
        if "type" not in creds_dict:
            st.error("Bitte trage die Service Account Daten in die secrets.toml ein.")
            st.stop()
            
        client = gspread.service_account_from_dict(creds_dict)
        spreadsheet_url = creds_dict.get("spreadsheet")
        sheet = client.open_by_url(spreadsheet_url)
        return sheet
    except Exception as e:
        st.error(f"Datenbankverbindung fehlgeschlagen. Bitte .streamlit/secrets.toml prüfen. Fehler: {e}")
        st.stop()

@retry(wait=wait_exponential(multiplier=1, min=1, max=10), stop=stop_after_attempt(5))
def get_worksheet(sheet_name):
    sheet = get_gspread_client()
    try:
        return sheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        # Create it if it doesn't exist
        st.info(f"Tabellenblatt '{sheet_name}' wird erstellt...")
        return sheet.add_worksheet(title=sheet_name, rows="1000", cols="20")

@retry(wait=wait_exponential(multiplier=1, min=1, max=10), stop=stop_after_attempt(5))
def _fetch_from_google(sheet_name):
    ws = get_worksheet(sheet_name)
    # Read everything into a dataframe
    # Drop rows where all elements are NaN
    df = get_as_dataframe(ws, evaluate_formulas=True)
    df = df.dropna(how='all')
    
    if df.empty or len(df.columns) == 0:
        return pd.DataFrame(columns=COLUMNS[sheet_name])
        
    return df

@st.cache_data(ttl=15)
def _load_data_internal(sheet_name):
    return _fetch_from_google(sheet_name)

def load_data(sheet_name):
    return _load_data_internal(sheet_name).copy()

@retry(wait=wait_exponential(multiplier=1, min=1, max=10), stop=stop_after_attempt(5))
def save_data(sheet_name, df, clear_cache=True):
    ws = get_worksheet(sheet_name)
    ws.clear()
    set_with_dataframe(ws, df, include_index=False)
    if clear_cache:
        _load_data_internal.clear()

def init_db():
    # Initialize all sheets
    for sheet in COLUMNS.keys():
        df = load_data(sheet)
        
        # specific init logic
        if sheet == SHEET_USER_DB and df.empty:
            pwd_hash = hashlib.sha256("tsc2026".encode()).hexdigest()
            new_user = pd.DataFrame([{"Username": "kai", "Password_Hash": pwd_hash, "Gewicht_kg": 85, "Groesse_cm": 185, "Geschlecht": "Männlich", "Rolle": "Admin", "Profilbild_Url": "🤿"}])
            df = pd.concat([df, new_user], ignore_index=True)
            save_data(SHEET_USER_DB, df)
            
        elif sheet == SHEET_GETRAENKE_DB and df.empty:
            master_drinks = generate_master_drinks()
            drinks_df = pd.DataFrame(master_drinks, columns=COLUMNS[SHEET_GETRAENKE_DB])
            save_data(SHEET_GETRAENKE_DB, drinks_df)
            
        elif sheet == SHEET_ACTIVATION_CODES and df.empty:
            import random
            codes = []
            for _ in range(20):
                random_digits = f"{random.randint(1000, 9999)}"
                codes.append({
                    "Code": f"TSC-{random_digits}",
                    "Used": "FALSE",
                    "Used_By": "",
                    "Used_At": ""
                })
            codes_df = pd.DataFrame(codes, columns=COLUMNS[SHEET_ACTIVATION_CODES])
            save_data(SHEET_ACTIVATION_CODES, codes_df)

# Run init on app startup
if "db_initialized" not in st.session_state:
    init_db()
    st.session_state.db_initialized = True

# --- AUTH HELPERS ---
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def login_user(username, password, is_hashed=False):
    users_df = load_data(SHEET_USER_DB)
    pwd_hash = password if is_hashed else hash_password(password)
    user = users_df[(users_df['Username'].str.lower() == username.lower()) & (users_df['Password_Hash'] == pwd_hash)]
    if not user.empty:
        st.session_state.logged_in = True
        st.session_state.username = user.iloc[0]['Username']
        st.session_state.role = user.iloc[0]['Rolle']
        st.session_state.gewicht = float(user.iloc[0]['Gewicht_kg'])
        st.session_state.groesse = float(user.iloc[0]['Groesse_cm'])
        st.session_state.geschlecht = user.iloc[0]['Geschlecht']
        return True
    return False

def register_user(username, password, gewicht, groesse, geschlecht, profilbild, activation_code):
    users_df = load_data(SHEET_USER_DB)
    if not users_df.empty and username.lower() in users_df['Username'].str.lower().values:
        return False, "Username bereits vergeben."
        
    codes_df = load_data(SHEET_ACTIVATION_CODES)
    code_row = codes_df[codes_df['Code'] == activation_code]
    if code_row.empty:
        return False, "Ungültiger Aktivierungscode."
    if str(code_row.iloc[0]['Used']).upper() == "TRUE":
        return False, "Aktivierungscode wurde bereits verwendet."
        
    # Mark code as used
    codes_df.loc[codes_df['Code'] == activation_code, 'Used'] = "TRUE"
    codes_df.loc[codes_df['Code'] == activation_code, 'Used_By'] = username
    codes_df.loc[codes_df['Code'] == activation_code, 'Used_At'] = get_now_berlin().strftime("%Y-%m-%d %H:%M:%S")
    save_data(SHEET_ACTIVATION_CODES, codes_df)
    
    pwd_hash = hash_password(password)
    new_user = pd.DataFrame([{
        "Username": username,
        "Password_Hash": pwd_hash,
        "Gewicht_kg": gewicht,
        "Groesse_cm": groesse,
        "Geschlecht": geschlecht,
        "Rolle": "User",
        "Profilbild_Url": profilbild
    }])
    users_df = pd.concat([users_df, new_user], ignore_index=True)
    save_data(SHEET_USER_DB, users_df)
    return True, "Erfolgreich registriert!"

# --- PROMILLE RECHNER ---
def calc_promille(username):
    # Load user data
    users_df = load_data(SHEET_USER_DB)
    user_row = users_df[users_df['Username'] == username]
    if user_row.empty: return 0.0
    
    gewicht = float(user_row.iloc[0]['Gewicht_kg'])
    groesse = float(user_row.iloc[0]['Groesse_cm'])
    geschlecht = user_row.iloc[0]['Geschlecht']
    
    # Calculate Reduction Factor (r) according to standard Widmark
    # ANPASSUNG FÜR ERFAHRENE TRINKER (höherer Muskelanteil / Toleranz)
    # Standard-Mann: 0.70 -> Erfahren: 0.80
    # Standard-Frau: 0.60 -> Erfahren: 0.70
    if geschlecht == "Männlich":
        r = 0.80
    else:
        r = 0.70
        
    if gewicht <= 0: gewicht = 80.0 # Fallback safety
    
    # Load logs for today
    logs_df = load_data(SHEET_KONSUM_LOG)
    logs_df['Zeitstempel'] = pd.to_datetime(logs_df['Zeitstempel'])
    
    now = get_now_berlin()
    user_logs = logs_df[(logs_df['Username'].astype(str).str.strip().str.lower() == str(username).strip().lower())]
    if user_logs.empty: return 0.0
    
    user_logs = user_logs.sort_values('Zeitstempel')
    
    current_promille = 0.0
    last_time = None
    
    # Abbau-Rate für erfahrene Trinker (Standard 0.15, Erfahren ca. 0.20 - 0.22)
    abbau_rate_pro_stunde = 0.20
    
    for _, row in user_logs.iterrows():
        t = row['Zeitstempel']
        ml = float(row['Menge_ml'])
        vol = float(row['Alk_Vol'])
        
        if last_time is not None:
            hours_passed = (t - last_time).total_seconds() / 3600.0
            if hours_passed > 0:
                current_promille = max(0.0, current_promille - (hours_passed * abbau_rate_pro_stunde))
                
        a = ml * (vol / 100) * 0.8
        current_promille += a / (gewicht * r)
        last_time = t
        
    if last_time is not None:
        hours_passed = (now - last_time).total_seconds() / 3600.0
        if hours_passed > 0:
            current_promille = max(0.0, current_promille - (hours_passed * abbau_rate_pro_stunde))
            
    return round(current_promille, 2)

def get_symptom_info(promille):
    if promille < 0.1:
        return "Nüchtern. Bereit für den Tauchgang! 🤿"
    elif promille <= 0.5:
        return "Bis 0.5‰: Leicht angetrunken / beginnender Tunnelblick."
    elif promille <= 1.0:
        return "0.5-1.0‰: Schwimmstadium. Enthemmung, leichte Koordinationsstörungen."
    elif promille <= 2.0:
        return "1.0-2.0‰: Tieftauchgang / Lallen. Deutliche Sprach- und Gleichgewichtsstörungen."
    else:
        return "Ab 2.0‰: Schwerer Rausch. *Hinweis: Bei einem nicht-alkoholkranken Menschen könnten bei dieser Promillezahl schwere Vergiftungssymptomatiken auftreten...*"

# --- VIEWS ---
def login_view():
    try:
        st.image("banner.png", use_column_width=True)
    except Exception as e:
        st.markdown("<h1 style='text-align: center;'>🤿 Tauchsportclub<br>Deep Dive Counter</h1>", unsafe_allow_html=True)
    
    tab1, tab2 = st.tabs(["Login", "Registrierung"])
    
    with tab1:
        with st.container(border=True):
            st.subheader("Login")
            with st.form("login_form"):
                l_user = st.text_input("Username", key="l_user", autocomplete="username")
                l_pass = st.text_input("Passwort", type="password", key="l_pass", autocomplete="current-password")
                submitted = st.form_submit_button("Einloggen", use_container_width=True)
                if submitted:
                    if login_user(l_user, l_pass):
                        st.query_params["user"] = l_user
                        st.query_params["hash"] = hash_password(l_pass)
                        import time
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("Falscher Username oder Passwort.")
    with tab2:
        with st.container(border=True):
            st.subheader("Neuer Taucher")
            r_user = st.text_input("Username", key="r_user")
            r_pass = st.text_input("Passwort", type="password", key="r_pass")
            r_code = st.text_input("Aktivierungscode", key="r_code", placeholder="Z.B. TSC-1234")
            r_gew = st.number_input("Gewicht (kg)", min_value=30.0, max_value=200.0, value=75.0)
            r_groesse = st.number_input("Größe (cm)", min_value=120, max_value=230, value=175)
            r_geschlecht = st.selectbox("Geschlecht", ["Männlich", "Weiblich"])
            
            st.write("Profilbild auswählen oder hochladen:")
            r_pic_emoji = st.selectbox("Emoji-Avatar", ["🤿", "🦈", "🐙", "🍺", "🍹", "🐋"])
            r_pic_file = st.file_uploader("Oder eigenes Bild hochladen (Optional)", type=["jpg", "jpeg", "png"])
            
            if st.button("Registrieren", use_container_width=True):
                if r_user and r_pass and r_code:
                    # Handle Image Upload (compress to Base64)
                    profilbild = r_pic_emoji
                    if r_pic_file is not None:
                        try:
                            img = Image.open(r_pic_file)
                            img.thumbnail((150, 150)) # Resize to small avatar
                            # Convert to RGB to ensure JPEG compatibility
                            if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                            
                            buffer = io.BytesIO()
                            img.save(buffer, format="JPEG", quality=70)
                            encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
                            profilbild = f"data:image/jpeg;base64,{encoded}"
                        except Exception as e:
                            st.warning("Bild konnte nicht verarbeitet werden. Nutze Emoji.")
                            
                    success, msg = register_user(r_user, r_pass, r_gew, r_groesse, r_geschlecht, profilbild, r_code)
                    if success:
                        st.success(msg + " Bitte logge dich nun ein.")
                    else:
                        st.error(msg)
                else:
                    st.error("Bitte alle Pflichtfelder ausfüllen.")

def generate_whatsapp_link(username, anzahl, marke, sorte, nr_heute, nr_jahr):
    """Generiert einen wa.me-Link mit vorformulierter, sauber formatierter Nachricht."""
    import urllib.parse
    # Visuelle Darstellung: bis zu 10 Bier-Emojis für heute
    if nr_heute <= 10:
        heute_visual = "🍺" * nr_heute
    else:
        heute_visual = "🍺" * 10 + f" +{nr_heute - 10}"
    msg = (
        f"🍺 {username} hat gerade eingecheckt\n"
        f"\n"
        f"*{anzahl}x {marke}*\n"
        f"_{sorte}_\n"
        f"\n"
        f"Heute: {heute_visual}\n"
        f"{get_now_berlin().year}: {nr_jahr} Bier insgesamt"
    )
    encoded = urllib.parse.quote(msg)
    return f"https://wa.me/?text={encoded}"

def book_drink_now(marke, sorte, menge, alk_vol, anzahl=1, buchungs_zeit=None, lat=None, lon=None):
    if buchungs_zeit is None:
        buchungs_zeit = get_now_berlin()
    logs_df = load_data(SHEET_KONSUM_LOG)
    new_logs = []
    for _ in range(anzahl):
        new_logs.append({
            "Log_ID": str(uuid.uuid4()),
            "Zeitstempel": buchungs_zeit.strftime("%Y-%m-%d %H:%M:%S"),
            "Username": st.session_state.username,
            "Marke": marke,
            "Sorte": sorte,
            "Menge_ml": menge,
            "Alk_Vol": alk_vol,
            "latitude": lat,
            "longitude": lon
        })
    logs_df = pd.concat([logs_df, pd.DataFrame(new_logs)], ignore_index=True)
    save_data(SHEET_KONSUM_LOG, logs_df)
    
    # Statistiken für WA-Nachricht berechnen (nach dem Speichern)
    user_logs = logs_df[logs_df['Username'] == st.session_state.username].copy()
    user_logs['Zeitstempel'] = pd.to_datetime(user_logs['Zeitstempel'])
    heute = datetime.date.today()
    dieses_jahr = heute.year
    nr_heute = len(user_logs[user_logs['Zeitstempel'].dt.date == heute])
    nr_jahr = len(user_logs[user_logs['Zeitstempel'].dt.year == dieses_jahr])
    
    st.session_state['show_success_popup'] = True
    st.session_state['last_wa_link'] = generate_whatsapp_link(st.session_state.username, anzahl, marke, sorte, nr_heute, nr_jahr)
    st.session_state['last_booked_label'] = f"{anzahl}x {marke}"
    st.rerun()

@st.dialog("🍻 Prost!")
def booking_success_popup(wa_link, label):
    st.markdown(f"""
    <div style='text-align:center; padding: 1rem 0;'>
        <div style='font-size: 3rem;'>🎉</div>
        <h2 style='margin: 0.5rem 0; color: #27ae60;'>Erfolgreich eingebucht!</h2>
        <p style='color: #aaa; font-size: 1.1rem;'><strong>{label}</strong> wurde verbucht.</p>
    </div>
    """, unsafe_allow_html=True)
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("❌ Schließen", use_container_width=True):
            st.rerun()
    with col2:
        st.link_button("📲 WhatsApp", wa_link, use_container_width=True, type="primary")

import requests
from pyzbar.pyzbar import decode
from PIL import Image
import io

def decode_barcode(image_file):
    try:
        img = Image.open(image_file)
        decoded_objects = decode(img)
        if decoded_objects:
            return decoded_objects[0].data.decode("utf-8")
        return None
    except Exception as e:
        return None

def fetch_open_food_facts(barcode):
    try:
        url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
        headers = {
            "User-Agent": "TauchsportLog/1.0 (kai@bischoff.de)"
        }
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == 1:
                product = data.get("product", {})
                marke = product.get("brands", "")
                sorte = product.get("product_name", "")
                
                # Wenn beides leer ist, gib None zurück
                if not marke and not sorte:
                    return None
                    
                # Clean up multiple brands
                if marke and "," in marke:
                    marke = marke.split(",")[0]
                    
                nutriments = product.get("nutriments", {})
                alk = nutriments.get("alcohol", 0.0)
                if not alk: alk = nutriments.get("alcohol_value", 0.0)
                
                menge = product.get("quantity", "")
                menge_ml = 500  # Default
                if "ml" in menge.lower():
                    try:
                        menge_ml = int(''.join(filter(str.isdigit, menge)))
                    except:
                        pass
                elif "cl" in menge.lower():
                    try:
                        menge_ml = int(''.join(filter(str.isdigit, menge))) * 10
                    except:
                        pass
                elif "l" in menge.lower() and "ml" not in menge.lower() and "cl" not in menge.lower():
                    try:
                        menge_str = ''.join(c for c in menge if c.isdigit() or c == '.' or c == ',')
                        menge_ml = int(float(menge_str.replace(',', '.')) * 1000)
                    except:
                        pass

                return {
                    "marke": marke,
                    "sorte": sorte,
                    "alk": float(alk),
                    "menge": menge_ml
                }
        return None
    except Exception as e:
        return None

def buchung_view():
    st.title("🍺 Getränke buchen")
    
    # --- GPS STANDORT ERFASSUNG ---
    if "gps_active" not in st.session_state:
        st.session_state.gps_active = False

    with st.container(border=True):
        st.markdown("<h4 style='margin-bottom: 0;'>📍 GPS-Standort für dieses Getränk</h4>", unsafe_allow_html=True)
        st.checkbox("Standort beim Buchen automatisch erfassen", key="gps_active")
        st.caption("Wird für deinen nächsten Besuch gemerkt.")
        
        final_lat = None
        final_lon = None
        
        if st.session_state.gps_active:
            from gps_component import get_gps_auto
            location = get_gps_auto(key="gps_location")
            
            if location and "lat" in location and "lon" in location:
                st.session_state['cached_lat'] = location["lat"]
                st.session_state['cached_lon'] = location["lon"]
            elif location and "error" in location:
                st.error(f"GPS Fehler: {location['error']}")
            
            # Immer aus Cache lesen
            final_lat = st.session_state.get('cached_lat')
            final_lon = st.session_state.get('cached_lon')
            
            if final_lat and final_lon:
                st.success(f"🟢 Standort-Erfassung ist AKTIV")
                st.info(f"📡 {final_lat:.4f}, {final_lon:.4f}")
            else:
                st.warning("🔄 GPS wird gesucht...")
        else:
            st.info("🔴 Standort-Erfassung ist AUS")
            st.session_state.pop('cached_lat', None)
            st.session_state.pop('cached_lon', None)
    
    # QUICK ACCESS
    logs_df = load_data(SHEET_KONSUM_LOG)
    my_logs = logs_df[logs_df['Username'] == st.session_state.username]
    if not my_logs.empty:
        # Get last 5 unique drinks
        recent = my_logs.drop_duplicates(subset=['Marke', 'Sorte'], keep='last').tail(5)
        if not recent.empty:
            st.write("**⚡ Quick-Booking (Nochmal das Gleiche):**")
            cols = st.columns(len(recent))
            for idx, (_, row) in enumerate(recent.iterrows()):
                with cols[idx]:
                    # Format text cleanly in one line to prevent UI breaking
                    btn_text = f"{row['Marke']} {row['Sorte'][:12]}" 
                    if len(btn_text) > 20: btn_text = btn_text[:17] + "..."
                    
                    if st.button(f"⚡ {btn_text}", key=f"qb_{row['Log_ID']}", use_container_width=True, help=f"{row['Marke']} {row['Sorte']}"):
                        book_drink_now(row['Marke'], row['Sorte'], float(row['Menge_ml']), float(row['Alk_Vol']), 1, None, final_lat, final_lon)
            st.divider()
    
    getraenke_df = load_data(SHEET_GETRAENKE_DB)
    if 'Barcode' not in getraenke_df.columns:
        getraenke_df['Barcode'] = ""
        
    drink_options = getraenke_df.apply(lambda r: f"{r['Marke']} {r['Sorte']} ({r['Standard_Menge_ml']}ml)", axis=1).tolist()
    
    if "buchung_tab_val" not in st.session_state:
        st.session_state.buchung_tab_val = "🍻 Aus Datenbank wählen"

    def change_tab():
        st.session_state.buchung_tab_val = st.session_state.radio_buchung_tab

    tab_options = ["🍻 Aus Datenbank wählen", "📷 Barcode einscannen", "➕ Eigenes Getränk anlegen"]
    try:
        idx = tab_options.index(st.session_state.buchung_tab_val)
    except:
        idx = 0

    tab_selection = st.radio(
        "Aktion wählen:",
        tab_options,
        index=idx,
        horizontal=True,
        label_visibility="collapsed",
        key="radio_buchung_tab",
        on_change=change_tab
    )
    
    # Der aktuelle Tab ist st.session_state.buchung_tab_val
    if st.session_state.buchung_tab_val == "🍻 Aus Datenbank wählen":
        with st.container(border=True):
            st.write("**Schnellsuche:**")
            search_term = st.text_input("🔍 Suche nach Marke oder Sorte (z.B. Licher, Wodka...)", key="search_drink")
            
            filtered_options = drink_options
            if search_term:
                search_tokens = search_term.lower().split()
                search_nospace = search_term.lower().replace(" ", "")
                
                filtered_options = []
                for d in drink_options:
                    d_lower = d.lower()
                    d_nospace = d_lower.replace(" ", "")
                    # Match if ALL words are in the string (e.g. "paul weiz" -> "Paulaner Weizen")
                    # OR if the string without spaces matches (e.g. "brewdog" -> "Brew Dog")
                    if all(t in d_lower for t in search_tokens) or (search_nospace in d_nospace):
                        filtered_options.append(d)
                
            selected_option = st.selectbox("Was trinkst du?", filtered_options)
            
            anzahl = st.number_input("Anzahl", min_value=1, max_value=10, value=1, key="anz_db")
            
            mode = st.radio("Zeitpunkt", ["Jetzt live einbuchen", "Nachtragen"], key="mode_db")
            buchungs_zeit = get_now_berlin()
            if mode == "Nachtragen":
                manual_time = st.time_input("Uhrzeit auswählen", key="time_db")
                buchungs_zeit = datetime.datetime.combine(datetime.date.today(), manual_time)
                if buchungs_zeit > get_now_berlin():
                    buchungs_zeit -= datetime.timedelta(days=1)
                    
            if st.button("Einlochen 🎯", use_container_width=True, key="btn_db"):
                if not selected_option:
                    st.error("Bitte wähle ein Getränk aus.")
                else:
                    idx = drink_options.index(selected_option)
                    row = getraenke_df.iloc[idx]
                    marke = row['Marke']
                    sorte = row['Sorte']
                    menge = row['Standard_Menge_ml']
                    alk_vol = row['Alkoholgehalt_Vol']
                    book_drink_now(marke, sorte, menge, alk_vol, anzahl, buchungs_zeit, final_lat, final_lon)

    elif st.session_state.buchung_tab_val == "📷 Barcode einscannen":
        with st.container(border=True):
            st.write("Scanne den Barcode auf der Flasche/Dose, um das Getränk automatisch zu finden.")
            camera_image = st.camera_input("Barcode scannen", key="cam_barcode")
            
            if camera_image:
                with st.spinner("Analysiere Barcode..."):
                    barcode = decode_barcode(camera_image)
                    if barcode:
                        st.success(f"Barcode erkannt: {barcode}")
                        
                        match = getraenke_df[getraenke_df["Barcode"].astype(str) == str(barcode)]
                        if not match.empty:
                            row = match.iloc[0]
                            st.info(f"✅ Getränk in Datenbank gefunden: **{row['Marke']} {row['Sorte']}** ({row['Standard_Menge_ml']}ml)")
                            
                            anzahl_sc = st.number_input("Anzahl", min_value=1, max_value=10, value=1, key="anz_sc")
                            if st.button("Jetzt live einbuchen 🎯", use_container_width=True, key="btn_sc"):
                                book_drink_now(row['Marke'], row['Sorte'], float(row['Standard_Menge_ml']), float(row['Alkoholgehalt_Vol']), anzahl_sc, get_now_berlin(), final_lat, final_lon)
                        else:
                            st.warning("Getränk nicht in lokaler Datenbank.")
                            with st.spinner("Suche in globaler Datenbank (Open Food Facts)..."):
                                product_data = fetch_open_food_facts(barcode)
                                
                            if product_data:
                                st.info(f"🌐 Online gefunden: **{product_data['marke']} {product_data['sorte']}** ({product_data['menge']}ml, {product_data['alk']}%)")
                                
                                anzahl_api = st.number_input("Anzahl", min_value=1, max_value=10, value=1, key="anz_api")
                                if st.button("Für alle Speichern & Jetzt live einbuchen 🎯", use_container_width=True, key="btn_api"):
                                    new_drink = pd.DataFrame([{
                                        "Marke": product_data['marke'], 
                                        "Sorte": product_data['sorte'], 
                                        "Alkoholgehalt_Vol": product_data['alk'], 
                                        "Standard_Menge_ml": product_data['menge'], 
                                        "Barcode": barcode
                                    }])
                                    getraenke_df = pd.concat([getraenke_df, new_drink], ignore_index=True)
                                    save_data(SHEET_GETRAENKE_DB, getraenke_df)
                                    book_drink_now(product_data['marke'], product_data['sorte'], float(product_data['menge']), float(product_data['alk']), anzahl_api, get_now_berlin(), final_lat, final_lon)
                                
                                st.write("---")
                                st.write("Möchtest du Name oder Alkoholgehalt noch anpassen?")
                                if st.button("Werte bearbeiten", use_container_width=True):
                                    st.session_state.prefill_barcode = barcode
                                    st.session_state.prefill_marke = product_data['marke']
                                    st.session_state.prefill_sorte = product_data['sorte']
                                    st.session_state.prefill_menge = int(product_data['menge'])
                                    st.session_state.prefill_alk = float(product_data['alk'])
                                    st.session_state.buchung_tab_val = "➕ Eigenes Getränk anlegen"
                                    st.rerun()
                            else:
                                st.error("🌐 Auch online leider unbekannt.")
                                st.write("Möchtest du dieses Getränk manuell anlegen?")
                                if st.button("Getränk mit gescanntem Barcode anlegen", use_container_width=True):
                                    st.session_state.prefill_barcode = barcode
                                    st.session_state.buchung_tab_val = "➕ Eigenes Getränk anlegen"
                                    st.rerun()
                    else:
                        st.error("Kein Barcode erkannt. Bitte achte auf gute Beleuchtung und halte den Code scharf in die Kamera.")

    elif st.session_state.buchung_tab_val == "➕ Eigenes Getränk anlegen":
        with st.container(border=True):
            if "prefill_barcode" in st.session_state:
                st.info("Unbekannter Barcode! Bitte trage das Getränk einmalig hier ein, danach kennt die App es für immer.")
            else:
                st.write("Ist dein Getränk nicht in der Liste? Lege es hier einmalig an:")
                
            marke_val = st.session_state.pop("prefill_marke", "")
            sorte_val = st.session_state.pop("prefill_sorte", "Manuell")
            menge_val = int(st.session_state.pop("prefill_menge", 330))
            alk_val = float(st.session_state.pop("prefill_alk", 5.0))
            barcode_val = st.session_state.pop("prefill_barcode", "")
                
            col1, col2 = st.columns(2)
            with col1:
                marke = st.text_input("Marke/Name", value=marke_val, key="m_marke")
                menge = st.number_input("Menge (ml)", min_value=10, max_value=2000, step=10, value=menge_val, key="m_menge")
            with col2:
                sorte = st.text_input("Sorte", value=sorte_val, key="m_sorte")
                alk_vol = st.number_input("Alkoholgehalt (Vol%)", min_value=0.0, max_value=100.0, step=0.1, value=alk_val, key="m_alk")
                
            barcode = st.text_input("Barcode (EAN) - optional", value=barcode_val, key="m_barcode")
                
            anzahl2 = st.number_input("Anzahl", min_value=1, max_value=10, value=1, key="anz_m")
            mode2 = st.radio("Zeitpunkt", ["Jetzt live einbuchen", "Nachtragen"], key="mode_m")
            buchungs_zeit2 = get_now_berlin()
            if mode2 == "Nachtragen":
                manual_time2 = st.time_input("Uhrzeit auswählen", key="time_m")
                buchungs_zeit2 = datetime.datetime.combine(datetime.date.today(), manual_time2)
                if buchungs_zeit2 > get_now_berlin():
                    buchungs_zeit2 -= datetime.timedelta(days=1)
                    
            if st.button("Trinken & für alle Speichern 🎯", use_container_width=True, key="btn_m"):
                if not marke:
                    st.error("Bitte eine Marke/einen Namen eintragen.")
                else:
                    new_drink = pd.DataFrame([{
                        "Marke": marke, "Sorte": sorte, "Alkoholgehalt_Vol": alk_vol, "Standard_Menge_ml": menge, "Barcode": barcode
                    }])
                    getraenke_df = pd.concat([getraenke_df, new_drink], ignore_index=True)
                    save_data(SHEET_GETRAENKE_DB, getraenke_df)
                    book_drink_now(marke, sorte, menge, alk_vol, anzahl2, buchungs_zeit2, final_lat, final_lon)
            
    # Gemeinsames Popup für alle Tabs
    if st.session_state.pop('show_success_popup', False):
        booking_success_popup(
            st.session_state.pop('last_wa_link', '#'),
            st.session_state.pop('last_booked_label', 'Getränk')
        )

    # Storno Bereich
    st.subheader("Letzte Buchungen (Storno)")
    logs_df = load_data(SHEET_KONSUM_LOG)
    my_logs = logs_df[logs_df['Username'] == st.session_state.username].copy()
    
    if not my_logs.empty:
        my_logs['Zeitstempel'] = pd.to_datetime(my_logs['Zeitstempel'])
        my_logs = my_logs.sort_values(by="Zeitstempel", ascending=False).head(5)
        
        for _, row in my_logs.iterrows():
            with st.container(border=True):
                colA, colB = st.columns([3, 1])
                with colA:
                    time_str = row['Zeitstempel'].strftime("%H:%M")
                    st.write(f"**{time_str}** | {row['Marke']} {row['Sorte']}")
                with colB:
                    st.markdown("<div class='storno-btn'>", unsafe_allow_html=True)
                    if st.button("❌ Storno", key=f"storno_{row['Log_ID']}", use_container_width=True):
                        # Delete from dataframe
                        logs_df = logs_df[logs_df['Log_ID'] != row['Log_ID']]
                        save_data(SHEET_KONSUM_LOG, logs_df)
                        st.toast("Buchung storniert.", icon="🗑️")
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("Noch keine Getränke heute gebucht.")

def statistik_view():
    if st.session_state.get('view_profile_of'):
        public_profile_view(st.session_state.view_profile_of)
        return
        
    st.title("🏆 Statistiken")
    
    users_df = load_data(SHEET_USER_DB)
    logs_df = load_data(SHEET_KONSUM_LOG)
    
    if logs_df.empty:
        st.info("Noch keine Daten vorhanden.")
        return
        
    stats_data = []
    for _, user_row in users_df.iterrows():
        uname = user_row['Username']
        user_logs = logs_df[logs_df['Username'] == uname].copy()
        
        gesamt_getraenke = len(user_logs)
        if gesamt_getraenke == 0:
            continue
            
        total_ml = pd.to_numeric(user_logs['Menge_ml'], errors='coerce').sum()
        gesamt_liter = round(total_ml / 1000, 2)
        
        user_logs['Zeitstempel'] = pd.to_datetime(user_logs['Zeitstempel'])
        now = pd.Timestamp.now()
        first_drink_date = user_logs['Zeitstempel'].min()
        days_active = (now - first_drink_date).days + 1
        avg_per_day = round(gesamt_getraenke / max(1, days_active), 2)
        
        daily_counts_raw = user_logs.groupby(user_logs['Zeitstempel'].dt.date).size()
        best_day_count = daily_counts_raw.max() if not daily_counts_raw.empty else 0
        
        promille = calc_promille(uname)
        fav_drink = user_logs['Marke'].value_counts().idxmax()
        
        stats_data.append({
            "Taucher": uname,
            "Getränke": gesamt_getraenke,
            "Ø pro Tag": avg_per_day,
            "Bester Tag": best_day_count,
            "Volumen (L)": gesamt_liter,
            "Fav. Drink": fav_drink,
            "Live Pegel (‰)": promille
        })
        
    if not stats_data:
        st.info("Noch keine Getränke verbucht.")
        return
        
    stats_df = pd.DataFrame(stats_data)
    stats_df = stats_df.sort_values(by="Getränke", ascending=False).reset_index(drop=True)
    
    if not stats_df.empty:
        winner = stats_df.iloc[0]
        winner_name = winner['Taucher']
        winner_row = users_df[users_df['Username'] == winner_name].iloc[0]
        pic = winner_row['Profilbild_Url']
        
        with st.container(border=True):
            col1, col2 = st.columns([0.15, 0.85])
            with col1:
                if pic.startswith("data:image"):
                    st.markdown(f'<img src="{pic}" style="border-radius: 50%; width: 50px; height: 50px; object-fit: cover;">', unsafe_allow_html=True)
                else:
                    st.markdown(f'<span style="font-size: 40px;">{pic}</span>', unsafe_allow_html=True)
            with col2:
                st.success(f"👑 **All-Time King:** Wir verneigen uns vor **{winner_name}** mit unfassbaren **{winner['Getränke']} Drinks** ({winner['Volumen (L)']} Liter)! Prost! 🍻")
            
            if st.button(f"🔍 Öffne das Profil von {winner_name}", use_container_width=True):
                st.session_state.view_profile_of = winner_name
                st.rerun()
    
    stats_df.index = stats_df.index + 1
    stats_df.index.name = "Rang"
    stats_df = stats_df.reset_index()
    
    st.divider()
    st.subheader("📈 All-Time Getränke Verlauf")
    
    if not logs_df.empty:
        import altair as alt
        
        chart_df = logs_df.copy()
        chart_df['Zeitstempel'] = pd.to_datetime(chart_df['Zeitstempel'])
        chart_df['Datum'] = chart_df['Zeitstempel'].dt.date
        
        daily_user_counts = chart_df.groupby(['Datum', 'Username']).size().reset_index(name='Getränke')
        
        all_dates = pd.date_range(start=daily_user_counts['Datum'].min(), end=daily_user_counts['Datum'].max())
        all_users = daily_user_counts['Username'].unique()
        
        idx = pd.MultiIndex.from_product([all_dates.date, all_users], names=['Datum', 'Username'])
        full_grid = pd.DataFrame(index=idx).reset_index()
        
        merged = pd.merge(full_grid, daily_user_counts, on=['Datum', 'Username'], how='left').fillna(0)
        merged = merged.sort_values(['Username', 'Datum'])
        merged['All-Time Getränke'] = merged.groupby('Username')['Getränke'].cumsum()
        
        # Finde den letzten Tag pro User, um Emojis/Bilder nur ganz rechts anzuzeigen (spart extrem viel Payload!)
        last_dates = merged.groupby('Username')['Datum'].max().reset_index()
        last_dates['Is_Last'] = True
        merged = pd.merge(merged, last_dates, on=['Username', 'Datum'], how='left')
        
        # Emojis & Bilder abrufen
        user_emoji_map = {}
        user_image_map = {}
        for _, r in users_df.iterrows():
            pic = str(r['Profilbild_Url'])
            if len(pic) < 10 and not pic.startswith("http"):
                user_emoji_map[r['Username']] = pic
                user_image_map[r['Username']] = None
            else:
                user_emoji_map[r['Username']] = ""
                user_image_map[r['Username']] = pic
                
        merged['Emoji'] = merged.apply(lambda row: user_emoji_map.get(row['Username'], "") if row['Is_Last'] == True else "", axis=1)
        merged['Image_Url'] = merged.apply(lambda row: user_image_map.get(row['Username'], None) if row['Is_Last'] == True else None, axis=1)
        
        # Namen für die Legende mit All-Time Anzahl erweitern und sortieren
        max_drinks = merged.groupby('Username')['All-Time Getränke'].max().to_dict()
        merged['Legend_Name'] = merged['Username'].apply(lambda u: f"({int(max_drinks[u])}) {u}")
        
        # Sortiere die Legende absteigend nach Anzahl
        ordered_legends = [f"({int(v)}) {k}" for k, v in sorted(max_drinks.items(), key=lambda item: item[1], reverse=True)]
        
        base = alt.Chart(merged).encode(
            x=alt.X('Datum:T', axis=alt.Axis(format='%d.%m.', tickCount='day', title='Datum')),
            y=alt.Y('All-Time Getränke:Q', title='Getränke Gesamt'),
            color=alt.Color('Legend_Name:N', sort=ordered_legends, legend=alt.Legend(title="Taucher", orient="right"))
        )
        
        line = base.mark_line(point=alt.OverlayMarkDef(size=60))
        
        text = base.transform_filter(
            'datum.Emoji != ""'
        ).mark_text(
            align='right',
            dx=-10,
            dy=-15,
            fontSize=16
        ).encode(
            text='Emoji:N'
        )
        
        image = base.transform_filter(
            'isValid(datum.Image_Url)'
        ).mark_image(
            align='right',
            dx=-15,
            dy=-15,
            width=25,
            height=25
        ).encode(
            url='Image_Url:N'
        )
        
        st.altair_chart((line + text + image).interactive(), use_container_width=True)
        
    st.divider()
    st.subheader("📋 Rangliste")
    st.dataframe(stats_df, use_container_width=True, hide_index=True)

def public_profile_view(uname):
    st.button("🔙 Zurück zur Übersicht", on_click=lambda: st.session_state.pop('view_profile_of', None))
    
    st.title(f"Profil von {uname}")
    
    users_df = load_data(SHEET_USER_DB)
    logs_df = load_data(SHEET_KONSUM_LOG)
    
    user_row = users_df[users_df['Username'] == uname]
    if user_row.empty:
        st.error("Benutzer nicht gefunden.")
        return
        
    pic = user_row.iloc[0]['Profilbild_Url']
    p_val = calc_promille(uname)
    
    col1, col2 = st.columns([0.2, 0.8])
    with col1:
        if pic.startswith("data:image"):
            st.markdown(f'<img src="{pic}" style="border-radius: 50%; width: 100px; height: 100px; object-fit: cover;">', unsafe_allow_html=True)
        else:
            st.markdown(f"<h1 style='margin:0;'>{pic}</h1>", unsafe_allow_html=True)
    with col2:
        st.write(f"**Aktueller Promillewert:** {p_val} ‰")
        user_logs = logs_df[logs_df['Username'] == uname].copy()
        if not user_logs.empty:
            fav_drink = user_logs['Marke'].value_counts().idxmax()
            st.write(f"**Lieblingsgetränk:** {fav_drink}")
            
            user_logs['Zeitstempel'] = pd.to_datetime(user_logs['Zeitstempel'])
            now = get_now_berlin()
            cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_logs = user_logs[user_logs['Zeitstempel'] >= cutoff]
            
            drinks_today = len(today_logs)
            liters_today = round(today_logs['Menge_ml'].astype(float).sum() / 1000.0, 2)
            st.write(f"**Heute getrunken:** {drinks_today} Getränke ({liters_today} Liter)")
    
    st.divider()
    
    if user_logs.empty:
        st.info("Noch keine Getränke verbucht.")
        return
        
    user_logs['Zeitstempel'] = pd.to_datetime(user_logs['Zeitstempel'])
    now = pd.Timestamp.now()
    
    all_time = len(user_logs)
    this_year = len(user_logs[user_logs['Zeitstempel'].dt.year == now.year])
    this_month = len(user_logs[(user_logs['Zeitstempel'].dt.year == now.year) & (user_logs['Zeitstempel'].dt.month == now.month)])
    
    start_of_week = now - pd.to_timedelta(now.dayofweek, unit='d')
    start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
    this_week = len(user_logs[user_logs['Zeitstempel'] >= start_of_week])
    
    first_drink_date = user_logs['Zeitstempel'].min()
    days_active = (now - first_drink_date).days + 1
    avg_per_day = round(all_time / max(1, days_active), 2)
    avg_per_active_day = round(user_logs.groupby(user_logs['Zeitstempel'].dt.date).size().mean(), 2)
    daily_counts_raw = user_logs.groupby(user_logs['Zeitstempel'].dt.date).size()
    best_day_count = daily_counts_raw.max() if not daily_counts_raw.empty else 0
    
    total_ml = pd.to_numeric(user_logs['Menge_ml'], errors='coerce').sum()
    total_liters = round(total_ml / 1000, 2)
    
    st.subheader("📊 Trink-Statistiken")
    c1, c2, c3, c_vol = st.columns(4)
    c1.metric("All-Time", f"{all_time}")
    c2.metric("Dieses Jahr", f"{this_year}")
    c3.metric("Dieser Monat", f"{this_month}")
    c_vol.metric("Volumen", f"{total_liters} L")
    
    c4, c5, c6, c7 = st.columns(4)
    c4.metric("Diese Woche", f"{this_week}")
    c5.metric("Ø pro Tag (Gesamt)", f"{avg_per_day}")
    c6.metric("Ø pro Party-Tag", f"{avg_per_active_day}")
    c7.metric("Bester Tag", f"{best_day_count}")
    
    st.divider()
    st.subheader("📈 Getränke über die Zeit")
    
    daily_counts = user_logs.groupby(user_logs['Zeitstempel'].dt.date).size().reset_index(name='Getränke')
    daily_counts = daily_counts.set_index('Zeitstempel')
    
    st.bar_chart(daily_counts)
    
    st.divider()
    st.subheader("📜 Buchungs-Historie")
    display_logs = user_logs[['Zeitstempel', 'Marke', 'Sorte', 'Menge_ml']].copy()
    display_logs = display_logs.sort_values(by='Zeitstempel', ascending=False)
    st.dataframe(display_logs, hide_index=True, use_container_width=True)

import io
import base64
from PIL import Image

@st.dialog("📸 Neue Story")
def upload_story_dialog():
    st.write("Zeig allen, was du gerade trinkst!")
    uploaded_file = st.file_uploader("Bild auswählen oder aufnehmen", type=["jpg", "jpeg", "png", "webp"])
    caption_text = st.text_input("Bildunterschrift (optional)", max_chars=100)
    
    if uploaded_file is not None:
        st.image(uploaded_file, caption="Vorschau", use_column_width=True)
        if st.button("🚀 Story posten", type="primary", use_container_width=True):
            upload_success = False
            try:
                with st.spinner("Bild wird verarbeitet & hochgeladen..."):
                    img = Image.open(uploaded_file)
                    # We must ensure the Base64 string is < 50,000 chars for Google Sheets!
                    # 1. Resize to max 800x800 for higher PPI (keeps aspect ratio)
                    img.thumbnail((800, 800), Image.Resampling.LANCZOS)
                
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                    
                quality = 80
                base64_data = ""
                # 2. Compress until it fits
                while True:
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=quality)
                    base64_data = base64.b64encode(buffer.getvalue()).decode()
                    if len(base64_data) < 45000 or quality <= 10:
                        break
                    quality -= 10
                
                
                stories_df = load_data(SHEET_STORIES)
                new_row = pd.DataFrame([{
                    "username": st.session_state.username,
                    "image_data": "data:image/jpeg;base64," + base64_data,
                    "timestamp": pd.Timestamp.now().isoformat(),
                    "caption": caption_text
                }])
                stories_df = pd.concat([stories_df, new_row], ignore_index=True)
                save_data(SHEET_STORIES, stories_df)
                
                st.success("Story online!")
                upload_success = True
            except Exception as e:
                st.error(f"Upload-Fehler: {e}")
                
            if upload_success:
                import time
                time.sleep(1)
                st.rerun()

@st.dialog("Story")
def view_story_dialog(username, story_idx, user_stories_df, ordered_active_users):
    story = user_stories_df.iloc[story_idx]
    image_data = story['image_data']
    
    try:
        ts = pd.to_datetime(story['timestamp'])
        time_formatted = ts.strftime("%d.%m.%Y, %H:%M")
    except:
        time_formatted = story['timestamp']
        
    st.markdown(f"<h4 style='text-align:center;'>Story von {username}</h4>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center; color:gray; font-size:14px;'>Hochgeladen am: {time_formatted} Uhr ({story_idx+1}/{len(user_stories_df)})</p>", unsafe_allow_html=True)
    st.markdown(f'<img src="{image_data}" style="width:100%; border-radius:10px;">', unsafe_allow_html=True)
    
    # --- LIKES LOGIC ---
    temp_likes_key = f"temp_likes_{username}_{story_idx}"
    if temp_likes_key in st.session_state:
        likes_str = st.session_state[temp_likes_key]
    else:
        likes_str = str(story.get('likes', ''))
        
    if likes_str.lower() == 'nan': likes_str = ''
    liked_by = [u.strip() for u in likes_str.split(',') if u.strip()]
    
    i_liked = st.session_state.username in liked_by
    like_icon = "❤️" if i_liked else "🤍"
    like_text = f"{like_icon} Fachgerecht ({len(liked_by)})"

    st.write("")
    
    # --- NAVIGATION, LIKE, & DELETE BUTTONS ---
    is_own_story = (username == st.session_state.username)
    if is_own_story:
        col1, col2, col_del, col3 = st.columns([2, 3, 1, 2])
    else:
        col1, col2, col3 = st.columns([2, 3, 2])
    
    curr_user_idx = ordered_active_users.index(username)
    has_prev = (story_idx > 0) or (curr_user_idx > 0)
    has_next = (story_idx < len(user_stories_df) - 1) or (curr_user_idx < len(ordered_active_users) - 1)
    
    with col1:
        if has_prev:
            if st.button("◀ Zurück", use_container_width=True, key=f"prev_btn_{username}_{story_idx}"):
                if story_idx > 0:
                    st.session_state.tracked_story_idx = story_idx - 1
                    st.query_params["view_story"] = username
                    st.query_params["story_idx"] = str(story_idx - 1)
                else:
                    prev_user = ordered_active_users[curr_user_idx - 1]
                    st.session_state.tracked_story_user = prev_user
                    st.session_state.tracked_story_idx = "last"
                    st.query_params["view_story"] = prev_user
                    st.query_params["story_idx"] = "last"
                st.rerun()
            
    with col2:
        def handle_like():
            if i_liked:
                liked_by.remove(st.session_state.username)
            else:
                liked_by.append(st.session_state.username)
            
            stories_df = load_data(SHEET_STORIES)
            if 'likes' not in stories_df.columns:
                stories_df['likes'] = ""
                
            # Match by exact timestamp to avoid base64 header collisions
            match_idx = stories_df[(stories_df['username'] == username) & (stories_df['timestamp'].astype(str) == str(story['timestamp']))].index
            
            # Fallback to exact image data match if timestamp mismatch happens
            if match_idx.empty:
                match_idx = stories_df[(stories_df['username'] == username) & (stories_df['image_data'] == story['image_data'])].index
            
            if not match_idx.empty:
                new_likes_str = ",".join(liked_by)
                stories_df.at[match_idx[0], 'likes'] = new_likes_str
                save_data(SHEET_STORIES, stories_df)
                
                # Update session state so the fragment sees it on rerender
                st.session_state[temp_likes_key] = new_likes_str
                
        # Use on_click to update state BEFORE the fragment rerenders
        st.button(like_text, type="primary" if i_liked else "secondary", use_container_width=True, key=f"like_btn_{username}_{story_idx}", on_click=handle_like)

    if is_own_story:
        with col_del:
            if st.button("🗑️", help="Story löschen", use_container_width=True, key=f"del_btn_{username}_{story_idx}"):
                with st.spinner("Lösche..."):
                    stories_df = load_data(SHEET_STORIES)
                    
                    # Match by username and normalized timestamp (YYYY-MM-DD HH:MM:SS)
                    target_ts = str(story['timestamp']).replace('T', ' ')[:19]
                    stories_df['norm_ts'] = stories_df['timestamp'].apply(lambda x: str(x).replace('T', ' ')[:19])
                    
                    drop_mask = (stories_df['username'] == username) & (stories_df['norm_ts'] == target_ts)
                    drop_idx = stories_df[drop_mask].index
                    
                    if not drop_idx.empty:
                        stories_df = stories_df.drop(drop_idx)
                        stories_df = stories_df.drop(columns=['norm_ts'])
                        save_data(SHEET_STORIES, stories_df)
                        st.success("Gelöscht!")
                        
                        if "view_story" in st.query_params:
                            del st.query_params["view_story"]
                        if "story_idx" in st.query_params:
                            del st.query_params["story_idx"]
                            
                        import time
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Story nicht gefunden!")
                    
    with col3:
        if has_next:
            if st.button("Weiter ▶", use_container_width=True, key=f"next_btn_{username}_{story_idx}"):
                if story_idx < len(user_stories_df) - 1:
                    st.session_state.tracked_story_idx = story_idx + 1
                    st.query_params["view_story"] = username
                    st.query_params["story_idx"] = str(story_idx + 1)
                else:
                    next_user = ordered_active_users[curr_user_idx + 1]
                    st.session_state.tracked_story_user = next_user
                    st.session_state.tracked_story_idx = 0
                    st.query_params["view_story"] = next_user
                    st.query_params["story_idx"] = "0"
                st.rerun()

    if liked_by:
        st.markdown(f"<p style='font-size:12px; color:gray; text-align:center;'>Fachgerecht: {', '.join(liked_by)}</p>", unsafe_allow_html=True)
    
    st.write("")
    if st.button("✖️ Schließen", use_container_width=True):
        if "view_story" in st.query_params: del st.query_params["view_story"]
        if "story_idx" in st.query_params: del st.query_params["story_idx"]
        st.rerun()

def render_stories_bar():
    # Load all users and stories
    users_df = load_data(SHEET_USER_DB)
    stories_df = load_data(SHEET_STORIES)
    
    # Filter active stories (last 48 hours) & CLEANUP
    if not stories_df.empty:
        stories_df['timestamp'] = pd.to_datetime(stories_df['timestamp'])
        now = pd.Timestamp.now()
        
        # Auto-Cleanup older than 48 hours
        valid_mask = stories_df['timestamp'] >= (now - pd.Timedelta(hours=48))
        if not valid_mask.all():
            stories_df = stories_df[valid_mask].copy()
            save_df = stories_df.copy()
            save_df['timestamp'] = save_df['timestamp'].dt.strftime('%Y-%m-%dT%H:%M:%S.%f')
            save_data(SHEET_STORIES, save_df)
            
        active_stories = stories_df
        active_users = set(active_stories['username'].unique())
    else:
        active_stories = pd.DataFrame()
        active_users = set()

    # Determine ordered_active_users for navigation
    ordered_active_users = []
    my_uname = st.session_state.username
    if my_uname in active_users:
        ordered_active_users.append(my_uname)
        
    other_active = sorted([u for u in active_users if u != my_uname])
    ordered_active_users.extend(other_active)

    # Handle Dialog Triggers from Query Params
    if st.query_params.get("upload_story"):
        del st.query_params["upload_story"]
        upload_story_dialog()
        
    # Check if a story is selected
    story_user = st.query_params.get("view_story")
    if story_user and story_user in active_users:
        
        # Check tracking to survive reruns correctly without losing index
        if st.session_state.get('tracked_story_user') == story_user:
            story_idx_val = st.session_state.get('tracked_story_idx', 0)
            user_stories = active_stories[active_stories['username'] == story_user].sort_values(by='timestamp', ascending=True)
            
            if story_idx_val == "last":
                story_idx = len(user_stories) - 1
            else:
                try:
                    story_idx = int(story_idx_val)
                    if story_idx >= len(user_stories) or story_idx < 0:
                        story_idx = 0
                except:
                    story_idx = 0
        else:
            story_idx_str = st.query_params.get("story_idx", "0")
            user_stories = active_stories[active_stories['username'] == story_user].sort_values(by='timestamp', ascending=True)
            
            if story_idx_str == "last":
                story_idx = len(user_stories) - 1
            else:
                try:
                    story_idx = int(story_idx_str)
                    if story_idx >= len(user_stories) or story_idx < 0:
                        story_idx = 0
                except:
                    story_idx = 0
                    
            st.session_state.tracked_story_user = story_user
            st.session_state.tracked_story_idx = story_idx
                
        view_story_dialog(story_user, story_idx, user_stories, ordered_active_users)

    import urllib.parse
    import time
    q_params = dict(st.query_params)
    
    q_params_upload = q_params.copy()
    q_params_upload["upload_story"] = "true"
    q_params_upload["t"] = str(int(time.time() * 1000))
    upload_link = "?" + urllib.parse.urlencode(q_params_upload)

    # Calculate who is currently active (drank in the last 30 minutes)
    logs_df = load_data(SHEET_KONSUM_LOG)
    drunk_users = set()
    if not logs_df.empty:
        logs_df['Zeitstempel'] = pd.to_datetime(logs_df['Zeitstempel'])
        now_time = pd.Timestamp.now()
        for u in users_df['Username']:
            u_logs = logs_df[logs_df['Username'] == u]
            if not u_logs.empty:
                last_drink = u_logs['Zeitstempel'].max()
                if (now_time - last_drink).total_seconds() <= 30 * 60:
                    drunk_users.add(u)

    html = '<div style="display: flex; overflow-x: auto; padding: 10px 0; gap: 15px; border-bottom: 1px solid #333; margin-bottom: 15px;">'
    
    # 1. Dedicated Upload Button
    html += f'''
    <div style="flex-shrink: 0; display: flex; flex-direction: column; align-items: center;">
        <a href="{upload_link}" target="_self" style="text-decoration: none; width: 65px; height: 65px; border-radius: 50%; background-color: #2b2b2b; display: flex; align-items: center; justify-content: center; border: 2px dashed #ff4b4b;">
            <span style="font-size: 30px; color: #ff4b4b; font-weight: bold;">+</span>
        </a>
        <div style="text-align: center; font-size: 12px; color: #ccc; margin-top: 5px; width: 70px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">Neu</div>
    </div>
    '''
    
    # 2. All Active Stories
    for uname in ordered_active_users:
        pic = users_df[users_df['Username'] == uname]['Profilbild_Url'].values[0]
        if not pic.startswith("data:image"):
            pic = "https://cdn.pixabay.com/photo/2015/10/05/22/37/blank-profile-picture-973460_1280.png"
            
        ring_style = "border: 3px solid #39ff14; padding: 2px;"
        
        q_params_view = q_params.copy()
        q_params_view["view_story"] = uname
        q_params_view["t"] = str(int(time.time() * 1000))
        link = "?" + urllib.parse.urlencode(q_params_view)
        
        status_dot = "🟢" if uname in drunk_users else "🔴"
        display_name = "Du" if uname == st.session_state.username else uname
        
        html += f'''
        <a href="{link}" target="_self" style="text-decoration: none; flex-shrink: 0; display: flex; flex-direction: column; align-items: center;">
            <img src="{pic}" style="width: 65px; height: 65px; border-radius: 50%; object-fit: cover; {ring_style}">
            <div style="text-align: center; font-size: 12px; color: #ccc; margin-top: 5px; width: 70px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">{status_dot} {display_name}</div>
        </a>
        '''
        
    html += '</div>'
    
    # Remove newlines to prevent Streamlit from rendering indented lines as Markdown code blocks
    html = html.replace('\n', '')
    
    st.markdown(html, unsafe_allow_html=True)

def social_view():
    if st.session_state.get('view_profile_of'):
        public_profile_view(st.session_state.view_profile_of)
        return
        
    render_stories_bar()
        
    st.title("Live")
    
    users_df = load_data(SHEET_USER_DB)
    logs_df = load_data(SHEET_KONSUM_LOG)
    

    
    active_users = []
    sober_users = []
    
    for idx, user_row in users_df.iterrows():
        uname = user_row['Username']
        p_val = calc_promille(uname)
        user_logs = logs_df[logs_df['Username'] == uname]
        
        user_data = {
            "uname": uname,
            "pic": user_row['Profilbild_Url'],
            "p_val": p_val,
            "user_logs": user_logs
        }
        if p_val > 0.0:
            active_users.append(user_data)
        else:
            sober_users.append(user_data)
            
    def render_user_cards(users_list, is_knuelle=True):
        if not users_list:
            st.write("Niemand in dieser Kategorie.")
            return
            
        for i, u in enumerate(users_list):
            uname = u["uname"]
            pic = u["pic"]
            p_val = u["p_val"]
            user_logs = u["user_logs"].copy()
            
            fav_drink = "-"
            if not user_logs.empty:
                fav_drink = user_logs['Marke'].value_counts().idxmax()
                
            if pic.startswith("data:image"):
                img_html = f'<img src="{pic}" style="border-radius: 50%; width: 40px; height: 40px; object-fit: cover; margin-right: 10px;">'
            else:
                img_html = f'<span style="font-size: 26px; margin-right: 8px;">{pic}</span>'
                
            is_active = False
            if not user_logs.empty:
                user_logs['Zeitstempel'] = pd.to_datetime(user_logs['Zeitstempel'])
                last_drink_time = user_logs['Zeitstempel'].max()
                now = pd.Timestamp.now()
                diff = now - last_drink_time
                if diff.total_seconds() <= 30 * 60:
                    is_active = True
                    
            status_badge = '<span style="color: #28a745; font-size: 0.7em; margin-left: auto; font-weight: bold;">🟢 Aktiv</span>' if is_active else '<span style="color: #6c757d; font-size: 0.7em; margin-left: auto;">⚪ Inaktiv</span>'
            
            border_color = "#ff4b4b" if is_knuelle else "#4b8bff"
            bg_color = "#1e1e1e"
            
            card_html = f"""
            <div style="background-color: {bg_color}; padding: 12px; border-radius: 8px; border-left: 5px solid {border_color}; margin-bottom: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.2);">
                <div style="display:flex; align-items:center; margin-bottom: 6px;">
                    {img_html}
                    <strong style="font-size:1.1em; color: #ffffff;">{uname}</strong>
                    {status_badge}
                </div>
                <div style="font-size: 0.85em; color: #aaaaaa; line-height: 1.4;">
                    <span style="background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px; margin-right: 5px;"><b>P:</b> <span style="color:{border_color}; font-weight:bold;">{p_val}‰</span></span>
                    <span style="background: rgba(255,255,255,0.05); padding: 2px 6px; border-radius: 4px;"><b>Fav:</b> {fav_drink}</span>
                </div>
            </div>
            """
            
            st.markdown(card_html, unsafe_allow_html=True)
            
            if st.button("📊 Profil", key=f"btn_{uname}", use_container_width=True):
                st.session_state.view_profile_of = uname
                st.rerun()

    st.subheader("Knülle (> 0.0 ‰)")
    active_users = sorted(active_users, key=lambda x: x['p_val'], reverse=True)
    render_user_cards(active_users, is_knuelle=True)
    
    st.divider()
    
    # --- LIVE FEED & TAGES RANGLISTE ---
    recent_logs = logs_df.copy()
    if not recent_logs.empty:
        col_feed, col_today = st.columns(2)
        recent_logs['Zeitstempel'] = pd.to_datetime(recent_logs['Zeitstempel'])
        now = pd.Timestamp.now()
        
        with col_feed:
            st.write("**Letzte Buchungen**")
            feed_logs = recent_logs.sort_values(by='Zeitstempel', ascending=False).head(100)
            with st.container(height=150):
                for _, r in feed_logs.iterrows():
                    diff = now - r['Zeitstempel']
                    mins = int(diff.total_seconds() // 60)
                    st.markdown(f"**{r['Username']}** trank **{r['Marke']}** <small style='color:gray;'>(vor {mins}m)</small>", unsafe_allow_html=True)
                    
        with col_today:
            st.write("**Heute getrunken**")
            today_logs = recent_logs[recent_logs['Zeitstempel'].dt.date == now.date()]
            with st.container(height=150):
                if not today_logs.empty:
                    daily_board = today_logs.groupby('Username').size().reset_index(name='Anzahl')
                    daily_board = daily_board.sort_values(by='Anzahl', ascending=False).reset_index(drop=True)
                    for i, row in daily_board.iterrows():
                        medal = "🥇" if i == 0 else ("🥈" if i == 1 else ("🥉" if i == 2 else "🔹"))
                        st.markdown(f"{medal} **{row['Username']}**: {row['Anzahl']} Drinks")
                else:
                    st.write("Noch keine Getränke heute.")
                    
    st.divider()
    
    st.subheader("Nüchtern (0.0 ‰)")
    render_user_cards(sober_users, is_knuelle=False)



def admin_view():
    st.title("🛠️ Admin-Bereich")
    
    if st.session_state.role != "Admin":
        st.error("Zugriff verweigert.")
        return
        
    st.subheader("Globales Log (Heute)")
    logs_df = load_data(SHEET_KONSUM_LOG)
    st.dataframe(logs_df, use_container_width=True)
    
    with st.container(border=True):
        st.markdown("<h3>🍻 Erweiterte Getränke-Matrix Importieren</h3>", unsafe_allow_html=True)
        st.write("Fügt die große Liste an internationalen Bieren und Weinen zur Datenbank hinzu.")
        if st.button("Jetzt Getränke-Erweiterung importieren"):
            neue_brauereien_int = [
                "Pilsner Urquell", "Budweiser Budvar", "Staropramen", "Krušovice", "Gambrinus",
                "Stella Artois", "Leffe (Blond/Bruin)", "Chouffe", "Duvel", "Grimbergen", 
                "Hoegaarden", "Chimay", "Delirium Tremens", "Kastel Beer",
                "John Smith's", "Newcastle Brown Ale", "London Pride", "Sharp's Doom Bar", 
                "BrewDog (Punk IPA)", "Stiegl", "Zipfer", "Ottakringer", "Gösser", "Puntigamer", 
                "Wieselburger", "Feldschlösschen", "Calanda", "Quöllfrisch", "Amstel", "Grolsch", 
                "Bavaria", "Hertog Jan", "Diekirch", "Bofferding", "Kronenbourg 1664", "Pelforth", 
                "Fischer", "San Miguel", "Estrella Damm", "Cruzcampo", "Mahou", "Alhambra", 
                "Super Bock", "Sagres", "Peroni (Nastro Azzurro)", "Moretti", "Ichnusa", "Messina", 
                "Carlsberg", "Tuborg", "Mikkeller", "Lapin Kulta", "Norrlands Guld", "Saku", 
                "Švyturys", "Miller Genuine Draft", "Coors Light", "Samuel Adams", "Brooklyn Brewery", 
                "Asahi Super Dry", "Sapporo", "Tsingtao", "Tiger Beer", "Singha", "Chang", "Quilmes"
            ]

            neue_brauereien_int.extend([
                "Bernard", "Kozel", "Zubr", "Tyskie", "Żywiec", "Lech", "Warka", "Okocim", 
                "Jupiler", "Brugse Zot", "Duchesse de Bourgogne", "Westmalle", "Rochefort", "Orval",
                "La Trappe", "Hertog Jan Weizener", "Gulpener", "Bavaria 8.6",
                "Eggenberg", "Murauer", "Schremser", "Hirter", "Schützengarten", "Chopfab",
                "Carling", "Tennent's", "Hobgoblin", "Beavertown", "Fuller's", "Smithwick's",
                "Estrella Galicia", "Moritz", "Ambar", "Sagres Bohemia", "Baladin", "Birra Moretti La Rossa",
                "Lapin Kulta", "Norrlands Guld", "Pelforth", "Fischer", "3 Fonteinen", "Põhjala",
                "Svijany", "Regent", "Zlatý Bažant (Slowakei)", "Šariš", "Kaper", "Lwówek", "Namysłów",
                "La Chouffe Blonde", "Mc Chouffe", "Duvel Tripel Hop", "Karmeliet Tripel", "Kwak",
                "St. Bernardus", "Tongerlo", "Affligem", "Delirium Red", "Lindemans (Kriek/Lambic)",
                "Heineken Silver", "Brand Brauerei", "Texels Skuumkoppe", "Jopen",
                "Gösser Stiftsbräu", "Murauer Märzen", "Villacher", "Fohrenburger", "Eggenberg Urbock",
                "Eichhof", "Appenzeller Bier", "Chopfab Hell", "Boxer Bier",
                "Guinness Hop House 13", "Kilkenny Irish Red Ale", "Carling Black Label", "Belhaven",
                "Samuel Smith's Taddy Porter", "Fuller's London Pride", "Sharp's Atlantic Pale Ale",
                "Estrella Damm Inedit", "Alhambra Reserva 1925", "Super Bock Stout", "Sagres Preta",
                "Birra Moretti Autentica", "Peroni Gran Riserva", "Ichnusa Non Filtrata", "Mythos (Griechenland)", "Fix",
                "Tuborg Grøn", "Carlsberg Elephant", "Mikkeller Peter, Pale and Mary", "AASS (Norwegen)",
                "Mack", "Karhu (Finnland)", "Olvi", "Aldaris (Lettland)", "Kalnapilis (Litauen)", "Kronenbourg Blanc"
            ])

            brauereien_de_extra = [
                "Schlenkerla (Bamberg)", "Andechs", "Weltenburger Kloster", "Riegele", "FrauGruber",
                "Felsgold", "Wernesgrüner", "Brinkhoff's", "Dortmunder Kronen", "Stauder", 
                "König Ludwig", "Allgäuer Brauhaus", "Alpirsbacher", "Distelhäuser", "Hochstift", 
                "Gessner", "Köthener", "Freiberger", "Lausitzer Porter", "Würzburger Hofbräu",
                "Tucher", "Grüner", "Schanzenbräu", "Karg", "Unertl", "Kneitinger", "Spital",
                "Weltenburger", "Arcobräu", "Graf Arco", "Falter", "Eichbaum", "Welser",
                "Gaffel Wiess", "Peters Kölsch", "Sion Kölsch", "Mühlen Kölsch", "Dom Kölsch",
                "Bolten Alt", "Schlüssel Alt", "Schumacher Alt", "Kürzer Alt", "Hannen Alt"
            ]

            brauereien_de_extra.extend([
                "Guxhavener", "Störtebeker", "Dithmarscher", "Herforder", "Barre", "Veltins Grevensteiner",
                "Hasseröder", "Freiberger", "Radeberger Brauerei", "Feldschlößchen (Dresden)", "Wernesgrüner",
                "Augustiner Maximator", "Tegernseer Max I. Joseph", "König Ludwig Dunkel", "Hacker-Pschorr Kellerbier",
                "Kulmbacher Edelherb", "Kapuziner (Weizen)", "Mönchshof Kellerbier", "Schanzenbräu Kehlkopf",
                "Maisel & Friends", "Crew Republic", "Kambium", "Hanscraft", "Tilmans Biere",
                "Gutmann (Weizen)", "Kuchlbauer", "Schneider Weisse Aventinus", "Schlenkerla Rauchbier Fastenbier",
                "Ayinger Celebrator", "Felsenkeller", "Pyraser", "Kaufbeuren Buron", "Zirndorfer",
                "Glaabsbräu", "Schmucker", "Pfungstädter", "Michelstädter Brauhaus", "Brauhaus Faust", 
                "Krone (Darmstadt)", "Eichbaum Ureich", "Brauhaus Knallhütte", "Hochstift Pils",
                "Schöfferhofer Weizen", "Zunft Kölsch", "Sester Kölsch", "Küppers Kölsch",
                "Uerige Sticke", "Brauerei zum Schlüssel", "Diebels Alt", "Frankenheim Alt",
                "Binding"
            ])
            
            sorten_de = [
                {"Sorte": "Pils (0.33l)", "Vol": 4.8, "Menge": 330},
                {"Sorte": "Pils (0.5l)", "Vol": 4.8, "Menge": 500},
                {"Sorte": "Helles (0.5l)", "Vol": 5.0, "Menge": 500},
                {"Sorte": "Export (0.5l)", "Vol": 5.2, "Menge": 500},
                {"Sorte": "Hefe-Weizen (0.5l)", "Vol": 5.5, "Menge": 500},
                {"Sorte": "Kristall-Weizen (0.5l)", "Vol": 5.5, "Menge": 500},
                {"Sorte": "Dunkelbier (0.5l)", "Vol": 5.1, "Menge": 500},
                {"Sorte": "Radler (0.33l)", "Vol": 2.5, "Menge": 330},
                {"Sorte": "Radler (0.5l)", "Vol": 2.5, "Menge": 500},
                {"Sorte": "Alkoholfrei (0.33l)", "Vol": 0.0, "Menge": 330},
                {"Sorte": "Alkoholfrei (0.5l)", "Vol": 0.0, "Menge": 500}
            ]

            neue_sorten_int = [
                {"Sorte": "Lager / Pils", "Vol": 5.0, "Menge": 330, "Preis": 3.00},
                {"Sorte": "Pale Ale / IPA", "Vol": 6.2, "Menge": 330, "Preis": 3.80},
                {"Sorte": "Belgian Blonde / Wit", "Vol": 6.6, "Menge": 330, "Preis": 4.00},
                {"Sorte": "Stout / Porter", "Vol": 4.5, "Menge": 440, "Preis": 3.50},
                {"Sorte": "Apple Cider", "Vol": 4.5, "Menge": 500, "Preis": 3.50},
                {"Sorte": "Strong Ale (Triple)", "Vol": 8.5, "Menge": 330, "Preis": 4.50}
            ]

            neue_wein_sorten = [
                {"Marke": "Hauswein Weiß", "Kategorie": "Weißwein (Standard)", "Vol": 12.0},
                {"Marke": "Hauswein Rot", "Kategorie": "Rotwein (Standard)", "Vol": 13.0},
                {"Marke": "Hauswein Rosé", "Kategorie": "Roséwein (Standard)", "Vol": 12.0},
                {"Marke": "Sekt (Hausmarke)", "Kategorie": "Schaumwein (Standard)", "Vol": 11.0},
                {"Marke": "Prosecco (Hausmarke)", "Kategorie": "Schaumwein (Standard)", "Vol": 10.5},
                {"Marke": "Glühwein", "Kategorie": "Heißgetränk", "Vol": 10.5},
                {"Marke": "Grauburgunder", "Kategorie": "Weißwein", "Vol": 12.5},
                {"Marke": "Riesling", "Kategorie": "Weißwein", "Vol": 12.0},
                {"Marke": "Chardonnay", "Kategorie": "Weißwein", "Vol": 13.0},
                {"Marke": "Sauvignon Blanc", "Kategorie": "Weißwein", "Vol": 12.5},
                {"Marke": "Primitivo", "Kategorie": "Rotwein", "Vol": 13.5},
                {"Marke": "Merlot", "Kategorie": "Rotwein", "Vol": 13.0},
                {"Marke": "Cabernet Sauvignon", "Kategorie": "Rotwein", "Vol": 14.0},
                {"Marke": "Provence Rosé", "Kategorie": "Roséwein", "Vol": 12.5},
                {"Marke": "Rotkäppchen Sekt", "Kategorie": "Sekt", "Vol": 11.0},
                {"Marke": "Moët & Chandon", "Kategorie": "Champagner", "Vol": 12.0}
            ]

            neue_wein_formen = [
                {"Typ": "Glas (klein/0.2l)", "Menge": 200, "Preis": 4.00, "Vol_Anpassung": 1.0},
                {"Typ": "Glas (groß/0.25l)", "Menge": 250, "Preis": 5.00, "Vol_Anpassung": 1.0},
                {"Typ": "Flasche (0.75l)", "Menge": 750, "Preis": 15.00, "Vol_Anpassung": 1.0},
                {"Typ": "Weinschorle Sauer (0.4l)", "Menge": 400, "Preis": 3.50, "Vol_Anpassung": 0.5},
                {"Typ": "Weinschorle Süß (0.4l)", "Menge": 400, "Preis": 3.50, "Vol_Anpassung": 0.5}
            ]

            new_drinks = []
            
            # Internationale Biere kombinieren
            for b in neue_brauereien_int:
                for s in neue_sorten_int:
                    new_drinks.append({
                        "Marke": b,
                        "Sorte": s["Sorte"],
                        "Alkoholgehalt_Vol": round(s["Vol"], 2),
                        "Standard_Menge_ml": s["Menge"]
                    })
                    
            # Deutsche Biere kombinieren
            for b in brauereien_de_extra:
                for s in sorten_de:
                    new_drinks.append({
                        "Marke": b,
                        "Sorte": s["Sorte"],
                        "Alkoholgehalt_Vol": round(s["Vol"], 2),
                        "Standard_Menge_ml": s["Menge"]
                    })
                    
            # Weine kombinieren
            for w in neue_wein_sorten:
                for d in neue_wein_formen:
                    calc_vol = w["Vol"] * d["Vol_Anpassung"]
                    new_drinks.append({
                        "Marke": w["Marke"],
                        "Sorte": f'{w["Kategorie"]} - {d["Typ"]}',
                        "Alkoholgehalt_Vol": round(calc_vol, 2),
                        "Standard_Menge_ml": d["Menge"]
                    })
            
            # Cocktails hinzufügen
            neue_cocktails = [
                {"Marke": "Caipirinha", "Sorte": "Cocktail (0.3l)", "Vol": 12.0, "Menge": 300},
                {"Marke": "Mojito", "Sorte": "Cocktail (0.3l)", "Vol": 12.0, "Menge": 300},
                {"Marke": "Long Island Iced Tea", "Sorte": "Cocktail-Stark (0.35l)", "Vol": 20.0, "Menge": 350},
                {"Marke": "Piña Colada", "Sorte": "Cocktail-Sahne (0.4l)", "Vol": 10.0, "Menge": 400},
                {"Marke": "Sex on the Beach", "Sorte": "Cocktail (0.3l)", "Vol": 10.0, "Menge": 300},
                {"Marke": "Tequila Sunrise", "Sorte": "Cocktail (0.3l)", "Vol": 11.0, "Menge": 300},
                {"Marke": "Zombie", "Sorte": "Cocktail-Stark (0.35l)", "Vol": 18.0, "Menge": 350},
                {"Marke": "Swimming Pool", "Sorte": "Cocktail (0.4l)", "Vol": 10.0, "Menge": 400},
                {"Marke": "Cuba Libre", "Sorte": "Cocktail (0.3l)", "Vol": 12.5, "Menge": 300},
                {"Marke": "Mai Tai", "Sorte": "Cocktail-Stark (0.3l)", "Vol": 17.0, "Menge": 300}
            ]
            neue_cocktails.extend([
                {"Marke": "Whiskey Sour", "Sorte": "Cocktail-Klassiker (0.2l)", "Vol": 14.0, "Menge": 200},
                {"Marke": "Aperol Sour", "Sorte": "Cocktail-Klassiker (0.2l)", "Vol": 9.5, "Menge": 200},
                {"Marke": "Gimlet", "Sorte": "Cocktail-Klassiker (0.1l)", "Vol": 22.0, "Menge": 100},
                {"Marke": "Manhattan", "Sorte": "Cocktail-Stark (0.1l)", "Vol": 25.0, "Menge": 100},
                {"Marke": "Negroni", "Sorte": "Cocktail-Stark (0.1l)", "Vol": 24.0, "Menge": 100},
                {"Marke": "Old Fashioned", "Sorte": "Cocktail-Stark (0.1l)", "Vol": 28.0, "Menge": 100},
                {"Marke": "White Russian", "Sorte": "Cocktail-Sahne (0.2l)", "Vol": 16.0, "Menge": 200},
                {"Marke": "Black Russian", "Sorte": "Cocktail (0.15l)", "Vol": 22.0, "Menge": 150},
                {"Marke": "Margarita", "Sorte": "Cocktail-Klassiker (0.12l)", "Vol": 20.0, "Menge": 120},
                {"Marke": "Cosmopolitan", "Sorte": "Cocktail-Klassiker (0.15l)", "Vol": 17.0, "Menge": 150}
            ])
            new_drinks.extend([{
                "Marke": c["Marke"],
                "Sorte": c["Sorte"],
                "Alkoholgehalt_Vol": round(c["Vol"], 2),
                "Standard_Menge_ml": c["Menge"]
            } for c in neue_cocktails])
            
            # Fertige Longdrinks hinzufügen
            fertige_longdrinks = [
                {"Marke": "Wodka Lemon", "Sorte": "Longdrink (0.3l)", "Vol": 5.0, "Menge": 300},
                {"Marke": "Wodka Orangensaft (Wodka O)", "Sorte": "Longdrink (0.3l)", "Vol": 5.0, "Menge": 300},
                {"Marke": "Wodka Energy", "Sorte": "Longdrink (0.25l)", "Vol": 6.0, "Menge": 250},
                {"Marke": "Bacardi Cola", "Sorte": "Longdrink (0.3l)", "Vol": 5.0, "Menge": 300},
                {"Marke": "Whiskey Cola (Charly)", "Sorte": "Longdrink (0.3l)", "Vol": 5.3, "Menge": 300},
                {"Marke": "Gin Tonic", "Sorte": "Longdrink (0.25l)", "Vol": 6.0, "Menge": 250},
                {"Marke": "Korn Fanta", "Sorte": "Longdrink (0.3l)", "Vol": 4.3, "Menge": 300},
                {"Marke": "Korn Cola", "Sorte": "Longdrink (0.3l)", "Vol": 4.3, "Menge": 300},
                {"Marke": "Asbach Cola", "Sorte": "Longdrink (0.3l)", "Vol": 5.1, "Menge": 300},
                {"Marke": "Campari Orange", "Sorte": "Longdrink (0.3l)", "Vol": 3.3, "Menge": 300},
                {"Marke": "Licor 43 mit Milch (Blond Angel)", "Sorte": "Longdrink (0.3l)", "Vol": 4.1, "Menge": 300},
                {"Marke": "Jägermeister Cola", "Sorte": "Longdrink (0.3l)", "Vol": 4.7, "Menge": 300},
                {"Marke": "Malibu Kirsch", "Sorte": "Longdrink (0.3l)", "Vol": 2.8, "Menge": 300},
                {"Marke": "Pernod Cola", "Sorte": "Longdrink (0.3l)", "Vol": 5.3, "Menge": 300}
            ]
            fertige_longdrinks.extend([
                {"Marke": "Southern Ginger", "Sorte": "Longdrink (0.3l)", "Vol": 4.7, "Menge": 300},
                {"Marke": "Campari Tonic", "Sorte": "Longdrink (0.25l)", "Vol": 4.0, "Menge": 250},
                {"Marke": "Malibu Sprite", "Sorte": "Longdrink (0.3l)", "Vol": 2.8, "Menge": 300},
                {"Marke": "Captain Cola", "Sorte": "Longdrink (0.3l)", "Vol": 4.7, "Menge": 300},
                {"Marke": "Havana Cola", "Sorte": "Longdrink (0.3l)", "Vol": 5.3, "Menge": 300},
                {"Marke": "Gin Wild Berry", "Sorte": "Longdrink (0.25l)", "Vol": 6.0, "Menge": 250},
                {"Marke": "Wodka Kirsch", "Sorte": "Longdrink (0.3l)", "Vol": 5.0, "Menge": 300},
                {"Marke": "Whiskey Ginger (Irland-Style)", "Sorte": "Longdrink (0.3l)", "Vol": 5.3, "Menge": 300}
            ])
            new_drinks.extend([{
                "Marke": l["Marke"],
                "Sorte": l["Sorte"],
                "Alkoholgehalt_Vol": round(l["Vol"], 2),
                "Standard_Menge_ml": l["Menge"]
            } for l in fertige_longdrinks])
            
            # Saison- & Heißgetränke
            saison_und_heiss = [
                {"Marke": "Glühwein Pur", "Sorte": "Heißgetränk (0.2l)", "Vol": 10.5, "Menge": 200},
                {"Marke": "Eierpunsch mit Sahne", "Sorte": "Heißgetränk (0.2l)", "Vol": 11.0, "Menge": 200},
                {"Marke": "Heiße Oma (Milch mit Cognac)", "Sorte": "Heißgetränk (0.2l)", "Vol": 8.0, "Menge": 200},
                {"Marke": "Pharisäer (Kaffee mit Rum)", "Sorte": "Heißgetränk (0.2l)", "Vol": 10.0, "Menge": 200},
                {"Marke": "Heißer Kirschglühwein", "Sorte": "Heißgetränk (0.2l)", "Vol": 10.5, "Menge": 200}
            ]
            new_drinks.extend([{
                "Marke": h["Marke"],
                "Sorte": h["Sorte"],
                "Alkoholgehalt_Vol": round(h["Vol"], 2),
                "Standard_Menge_ml": h["Menge"]
            } for h in saison_und_heiss])
            
            # Bar-Longdrinks
            bar_longdrinks = [
                {"Marke": "London Mule (Gin Mule)", "Sorte": "Klassiker (0.3l)", "Vol": 5.6, "Menge": 300},
                {"Marke": "Cuba Libre Premium (Havana 7)", "Sorte": "Premium-Mix (0.3l)", "Vol": 13.3, "Menge": 300},
                {"Marke": "Horse's Neck", "Sorte": "Bourbon-Mix (0.25l)", "Vol": 6.4, "Menge": 250},
                {"Marke": "El Diablo", "Sorte": "Tequila-Mix (0.3l)", "Vol": 7.5, "Menge": 300},
                {"Marke": "Gin Buck", "Sorte": "Klassiker (0.3l)", "Vol": 5.6, "Menge": 300}
            ]
            new_drinks.extend([{
                "Marke": b["Marke"],
                "Sorte": b["Sorte"],
                "Alkoholgehalt_Vol": round(b["Vol"], 2),
                "Standard_Menge_ml": b["Menge"]
            } for b in bar_longdrinks])
            
            # Spezial-Shots & Absacker
            spezial_shots = [
                {"Marke": "Jägermeister (Eiskalt)", "Sorte": "Kräuter (2cl)", "Vol": 35.0, "Menge": 20},
                {"Marke": "Fernet Branca", "Sorte": "Kräuter (2cl)", "Vol": 39.0, "Menge": 20},
                {"Marke": "Underberg", "Sorte": "Kräuter (2cl)", "Vol": 44.0, "Menge": 20},
                {"Marke": "Linie Aquavit", "Sorte": "Kloster-Shot (2cl)", "Vol": 41.5, "Menge": 20},
                {"Marke": "Kamikaze", "Sorte": "Wodka-Shot (4cl)", "Vol": 22.0, "Menge": 40},
                {"Marke": "Orgasmus", "Sorte": "Likör-Shot (2cl)", "Vol": 22.0, "Menge": 20},
                {"Marke": "Liquid Cocaine", "Sorte": "Stark-Shot (4cl)", "Vol": 26.0, "Menge": 40},
                {"Marke": "U-Boot (Korn in Pils)", "Sorte": "Spezial-Mix (220ml)", "Vol": 6.2, "Menge": 220}
            ]
            new_drinks.extend([{
                "Marke": s["Marke"],
                "Sorte": s["Sorte"],
                "Alkoholgehalt_Vol": round(s["Vol"], 2),
                "Standard_Menge_ml": s["Menge"]
            } for s in spezial_shots])
            
            
            df = load_data(SHEET_GETRAENKE_DB)
            df_new = pd.DataFrame(new_drinks)
            df_combined = pd.concat([df, df_new], ignore_index=True)
            
            # Nur echte Duplikate löschen, alte Sachen unberührt lassen! keep='first' erhält die alten
            df_combined.drop_duplicates(subset=["Marke", "Sorte", "Standard_Menge_ml"], keep="first", inplace=True)
            
            # Alphabetisch sortieren nach Marke
            df_combined.sort_values(by=["Marke", "Sorte"], inplace=True)
            
            save_data(SHEET_GETRAENKE_DB, df_combined)
            st.success("Erweiterung erfolgreich importiert! Die alten Daten sind sicher und alles ist alphabetisch sortiert.")
            
    with st.container(border=True):
        st.markdown("<h3 style='color: #ff4b4b;'>🚨 Abend beenden & Nullen</h3>", unsafe_allow_html=True)
        st.write("Dies verschiebt alle aktuellen Einträge in die Backup-Historie und leert das Live-Log.")
        
        confirm_reset = st.checkbox("Ja, ich bin mir absolut sicher und möchte das Live-Log leeren.", key="check_reset")
        if confirm_reset:
            if st.button("Jetzt durchführen", type="primary"):
                if not logs_df.empty:
                    backup_df = load_data(SHEET_BACKUP_HISTORY)
                    
                    # Add backup timestamp
                    logs_df['Backup_Zeitstempel'] = get_now_berlin().strftime("%Y-%m-%d %H:%M:%S")
                    
                    # Reorder to match backup columns
                    logs_df = logs_df[COLUMNS[SHEET_BACKUP_HISTORY]]
                    
                    # Append to backup
                    backup_df = pd.concat([backup_df, logs_df], ignore_index=True)
                    save_data(SHEET_BACKUP_HISTORY, backup_df)
                    
                    # Clear active log
                    empty_log = pd.DataFrame(columns=COLUMNS[SHEET_KONSUM_LOG])
                    save_data(SHEET_KONSUM_LOG, empty_log)
                    
                    st.success("Erfolgreich gesichert und genullt!")
                    st.rerun()
                else:
                    st.info("Log ist bereits leer.")

    with st.container(border=True):
        st.markdown("<h3 style='color: #ff4b4b;'>🗑️ Benutzer endgültig löschen</h3>", unsafe_allow_html=True)
        st.write("Löscht einen Benutzer und alle seine jemals getrunkenen Getränke aus der Live-Datenbank und dem Backup.")
        
        all_users = load_data(SHEET_USER_DB)['Username'].tolist()
        user_to_delete = st.selectbox("Benutzer auswählen", all_users, key="del_user")
        
        confirm_del = st.checkbox("Ja, ich möchte diesen Benutzer und alle seine Daten restlos vernichten.", key="check_del")
        if confirm_del:
            if st.button("Benutzer mitsamt aller Daten löschen", type="primary", key="del_btn"):
                if user_to_delete:
                    # 1. Aus User_DB löschen
                    u_df = load_data(SHEET_USER_DB)
                    u_df = u_df[u_df['Username'] != user_to_delete]
                    save_data(SHEET_USER_DB, u_df)
                    
                    # 2. Aus Live Konsum Log löschen
                    l_df = load_data(SHEET_KONSUM_LOG)
                    if not l_df.empty:
                        l_df = l_df[l_df['Username'] != user_to_delete]
                        save_data(SHEET_KONSUM_LOG, l_df)
                        
                    # 3. Aus Backup Historie löschen
                    b_df = load_data(SHEET_BACKUP_HISTORY)
                    if not b_df.empty:
                        b_df = b_df[b_df['Username'] != user_to_delete]
                        save_data(SHEET_BACKUP_HISTORY, b_df)
                        
                    st.success(f"Benutzer '{user_to_delete}' wurde erfolgreich und restlos aus allen Datenbanken vernichtet!")

def profil_view():
    st.title("👤 Mein Profil")
    users_df = load_data(SHEET_USER_DB)
    user_row = users_df[users_df['Username'] == st.session_state.username]
    if user_row.empty:
        st.error("Profil nicht gefunden.")
        return
        
    user_idx = user_row.index[0]
    curr_data = user_row.iloc[0]
    
    # --- PROFIL STATISTIKEN ---
    logs_df = load_data(SHEET_KONSUM_LOG)
    my_logs = logs_df[logs_df['Username'] == st.session_state.username].copy()
    if not my_logs.empty:
        my_logs['Zeitstempel'] = pd.to_datetime(my_logs['Zeitstempel'])
        now = get_now_berlin()
        cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_logs = my_logs[my_logs['Zeitstempel'] >= cutoff]
        
        drinks_today = len(today_logs)
        liters_today = round(today_logs['Menge_ml'].astype(float).sum() / 1000.0, 2)
        p_val = calc_promille(st.session_state.username)
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Getränke heute", drinks_today)
        c2.metric("Liter heute", f"{liters_today} L")
        c3.metric("Dein Promillewert", f"{p_val} ‰")
        st.divider()
    
    tab_data, tab_pw = st.tabs(["Profildaten ändern", "Passwort ändern"])
    
    with tab_data:
        with st.form("profil_form"):
            new_gew = st.number_input("Gewicht (kg)", min_value=30.0, max_value=200.0, value=float(curr_data['Gewicht_kg']))
            new_groesse = st.number_input("Größe (cm)", min_value=120, max_value=230, value=int(curr_data['Groesse_cm']))
            
            st.write("Aktuelles Profilbild:")
            if str(curr_data['Profilbild_Url']).startswith("data:image"):
                st.markdown(f'<img src="{curr_data["Profilbild_Url"]}" style="border-radius: 50%; width: 60px; height: 60px; object-fit: cover;">', unsafe_allow_html=True)
            else:
                st.write(curr_data['Profilbild_Url'])
                
            st.write("Neues Profilbild auswählen oder hochladen:")
            r_pic_emoji = st.selectbox("Emoji-Avatar", ["Beibehalten", "🤿", "🦈", "🐙", "🍺", "🍹", "🐋"])
            r_pic_file = st.file_uploader("Oder neues Bild hochladen", type=["jpg", "jpeg", "png"])
            
            if st.form_submit_button("Profil speichern"):
                profilbild = curr_data['Profilbild_Url']
                if r_pic_emoji != "Beibehalten":
                    profilbild = r_pic_emoji
                    
                if r_pic_file is not None:
                    try:
                        img = Image.open(r_pic_file)
                        img.thumbnail((150, 150))
                        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
                        buffer = io.BytesIO()
                        img.save(buffer, format="JPEG", quality=70)
                        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
                        profilbild = f"data:image/jpeg;base64,{encoded}"
                    except:
                        st.warning("Fehler beim Bild-Upload.")
                
                users_df.at[user_idx, 'Gewicht_kg'] = new_gew
                users_df.at[user_idx, 'Groesse_cm'] = new_groesse
                users_df.at[user_idx, 'Profilbild_Url'] = profilbild
                save_data(SHEET_USER_DB, users_df)
                st.success("Profil erfolgreich aktualisiert!")
                
    with tab_pw:
        with st.form("pw_form"):
            old_pw = st.text_input("Altes Passwort", type="password")
            new_pw = st.text_input("Neues Passwort", type="password")
            new_pw2 = st.text_input("Neues Passwort bestätigen", type="password")
            
            if st.form_submit_button("Passwort ändern"):
                if not old_pw or not new_pw:
                    st.error("Bitte alle Felder ausfüllen.")
                elif new_pw != new_pw2:
                    st.error("Die neuen Passwörter stimmen nicht überein.")
                elif hashlib.sha256(old_pw.encode()).hexdigest() != curr_data['Password_Hash']:
                    st.error("Altes Passwort ist falsch.")
                else:
                    users_df.at[user_idx, 'Password_Hash'] = hashlib.sha256(new_pw.encode()).hexdigest()
                    save_data(SHEET_USER_DB, users_df)
                    st.success("Passwort erfolgreich geändert!")

def welt_view():
    st.title("🌍 Weltkarte der Getränke")
    st.write("Hier siehst du, wo wir schon überall getrunken haben!")
    
    logs_df = load_data(SHEET_KONSUM_LOG)
    if logs_df.empty:
        st.info("Noch keine Getränke mit Standort gebucht.")
        return
        
    map_df = logs_df.copy()
    # Konvertiere Koordinaten in Floats
    map_df['latitude'] = pd.to_numeric(map_df['latitude'], errors='coerce')
    map_df['longitude'] = pd.to_numeric(map_df['longitude'], errors='coerce')
    
    # Lösche Reihen ohne gültige Koordinaten
    map_df = map_df.dropna(subset=['latitude', 'longitude'])
    
    if map_df.empty:
        st.info("Bisher wurden noch keine Getränke mit aktivierter Standort-Erfassung gebucht.")
        return
        
    # Anzahl der Getränke pro Standort (Gruppieren)
    st.map(map_df, latitude='latitude', longitude='longitude', size=150, color='#ff4b4b', zoom=1)
    
    st.caption(f"Insgesamt {len(map_df)} markierte Getränke auf der Welt.")

# --- MAIN LOGIC ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    
    # Try autologin via secure URL parameters
    saved_user = st.query_params.get("user")
    saved_hash = st.query_params.get("hash")
    if saved_user and saved_hash:
        login_user(saved_user, saved_hash, is_hashed=True)

if not st.session_state.logged_in:
    login_view()
else:
    try:
        st.image("banner.png", use_column_width=True)
    except Exception as e:
        pass
        
    # Top Navigation Bar
    col_nav, col_logout = st.columns([0.85, 0.15])
    with col_nav:
        st.write(f"Willkommen, **{st.session_state.username}** 🤿")
    with col_logout:
        if st.button("Logout", use_container_width=True):
            if "user" in st.query_params:
                del st.query_params["user"]
            if "hash" in st.query_params:
                del st.query_params["hash"]
            st.session_state.logged_in = False
            st.rerun()
            
    menu = ["Live", "Getränke buchen", "Statistiken", "Mein Profil", "Welt"]
    icons = ["people", "cup-hot", "bar-chart-line", "person", "globe"]
    if st.session_state.role == "Admin":
        menu.append("Admin-Bereich")
        icons.append("gear")
        
    choice = option_menu(
        menu_title=None,
        options=menu,
        icons=icons,
        default_index=0,
        orientation="horizontal",
        styles={
            "container": {"padding": "0!important", "margin-bottom": "1rem"},
            "icon": {"font-size": "18px"},
            "nav-link": {"font-size": "15px", "text-align": "center", "margin": "0px", "--hover-color": "#4b4b4b"},
            "nav-link-selected": {"background-color": "#ff4b4b"},
        }
    )
    
    # Reset deep-links when switching tabs, but NOT on initial load!
    if 'last_menu_choice' not in st.session_state:
        st.session_state.last_menu_choice = choice
    elif st.session_state.last_menu_choice != choice:
        st.session_state.last_menu_choice = choice
        if "view_story" in st.query_params: del st.query_params["view_story"]
        if "story_idx" in st.query_params: del st.query_params["story_idx"]
        st.session_state.pop('tracked_story_user', None)
        st.session_state.pop('tracked_story_idx', None)
        st.session_state.pop('view_profile_of', None)
        st.rerun()
            
    # Route to views
    if choice == "Getränke buchen":
        buchung_view()
    elif choice == "Statistiken":
        statistik_view()
    elif choice == "Live":
        social_view()
    elif choice == "Mein Profil":
        profil_view()
    elif choice == "Welt":
        welt_view()
    elif choice == "Admin-Bereich":
        admin_view()

