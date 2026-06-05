import pandas as pd
import streamlit as st

BADGES = [
    # Grundausbildung
    {"id": "b01", "name": "Rekrut", "rank": "Grundausbildung", "desc": "Das allererste Getränk gebucht.", "icon": "🎖️"},
    {"id": "b02", "name": "Wasserratte", "rank": "Grundausbildung", "desc": "Das erste Wasser getrunken.", "icon": "💧"},
    {"id": "b03", "name": "Erste Ortung", "rank": "Grundausbildung", "desc": "Ein Getränk mit GPS-Standort geloggt.", "icon": "📡"},
    {"id": "b04", "name": "Feierabend-Bier", "rank": "Grundausbildung", "desc": "Ein Getränk zwischen 17:00 und 19:00 Uhr.", "icon": "🌇"},
    {"id": "b05", "name": "Nachtwache", "rank": "Grundausbildung", "desc": "Ein Getränk zwischen 00:00 und 04:00 Uhr.", "icon": "🦉"},
    {"id": "b06", "name": "Wochenend-Dienst", "rank": "Grundausbildung", "desc": "Ein Getränk an einem Samstag oder Sonntag.", "icon": "🗓️"},
    
    # Gefreiter
    {"id": "b07", "name": "Gefreiter der Reserve", "rank": "Gefreiter", "desc": "10 Getränke insgesamt gebucht.", "icon": "🥉"},
    {"id": "b08", "name": "Frühschicht", "rank": "Gefreiter", "desc": "Ein Getränk zwischen 06:00 und 10:00 Uhr.", "icon": "🌅"},
    {"id": "b09", "name": "Doppelschlag", "rank": "Gefreiter", "desc": "Zwei Getränke innerhalb von 30 Minuten.", "icon": "⚡"},
    {"id": "b10", "name": "Halber Liter", "rank": "Gefreiter", "desc": "Ein Getränk mit genau 500ml.", "icon": "🍺"},
    {"id": "b11", "name": "Montags-Maler", "rank": "Gefreiter", "desc": "Ein Getränk an einem Montag.", "icon": "🏠"},
    {"id": "b12", "name": "Süßkram-Schütze", "rank": "Gefreiter", "desc": "Ein Mixgetränk, Cola oder Energy getrunken.", "icon": "🥤"},
    
    # Unteroffizier
    {"id": "b13", "name": "Unteroffizier vom Dienst", "rank": "Unteroffizier", "desc": "50 Getränke insgesamt.", "icon": "🥈"},
    {"id": "b14", "name": "Dauerfeuer", "rank": "Unteroffizier", "desc": "3 Tage am Stück getrunken (Streak).", "icon": "🔥"},
    {"id": "b15", "name": "Großkaliber", "rank": "Unteroffizier", "desc": "Ein Getränk mit mindestens 1000ml (Maß).", "icon": "🍻"},
    {"id": "b16", "name": "Hochprozentig", "rank": "Unteroffizier", "desc": "Ein Getränk mit mindestens 20% Alkohol.", "icon": "🥃"},
    {"id": "b17", "name": "Schnapsschütze", "rank": "Unteroffizier", "desc": "Einen Shot getrunken.", "icon": "🎯"},
    {"id": "b18", "name": "Kater-Kommando", "rank": "Unteroffizier", "desc": "Sonntagmorgen zwischen 06:00 und 12:00 Uhr.", "icon": "🤕"},
    
    # Offizier
    {"id": "b19", "name": "Stabsoffizier", "rank": "Offizier", "desc": "100 Getränke insgesamt.", "icon": "🥇"},
    {"id": "b20", "name": "Eisernes Kreuz am Tresen", "rank": "Offizier", "desc": "10 Getränke an einem einzigen Tag.", "icon": "🏅"},
    {"id": "b21", "name": "Marathon-Marsch", "rank": "Offizier", "desc": "7 Tage am Stück getrunken (Streak).", "icon": "🏃"},
    {"id": "b22", "name": "Weltbummler", "rank": "Offizier", "desc": "Getränke an 3 verschiedenen Tagen mit GPS.", "icon": "🌍"},
    {"id": "b23", "name": "Infanterie-Sturmabz.", "rank": "Offizier", "desc": "5 Shots an einem Tag.", "icon": "⚔️"},
    {"id": "b24", "name": "Bier-Baron", "rank": "Offizier", "desc": "50 klassische Biere getrunken.", "icon": "👑"},
    
    # General
    {"id": "b25", "name": "Feldherr", "rank": "General", "desc": "250 Getränke insgesamt.", "icon": "🎖️🎖️"},
    {"id": "b26", "name": "Legende der Zapfsäule", "rank": "General", "desc": "500 Getränke insgesamt.", "icon": "🏆"},
    {"id": "b27", "name": "Ritterkreuz", "rank": "General", "desc": "20 Getränke an einem einzigen Tag.", "icon": "💀"},
    {"id": "b28", "name": "Veteran", "rank": "General", "desc": "Seit über 30 Tagen aktiv.", "icon": "👴"},
    {"id": "b29", "name": "Generalinspekteur", "rank": "General", "desc": "An jedem Wochentag mindestens einmal getrunken.", "icon": "📅"},
    {"id": "b30", "name": "Sanitäter", "rank": "General", "desc": "20x Wasser getrunken.", "icon": "⚕️"}
]

def check_user_badges(user_entries_df):
    earned = []
    if user_entries_df.empty:
        return earned
        
    df = user_entries_df.copy()
    df['Zeitstempel'] = pd.to_datetime(df['Zeitstempel'], errors='coerce').dropna()
    if df.empty:
        return earned
        
    df = df.sort_values('Zeitstempel')
    
    total_drinks = len(df)
    
    # Grundausbildung
    if total_drinks >= 1:
        earned.append("b01")
    
    wasser_mask = df['Sorte'].str.contains("Wasser", case=False, na=False) | df['Marke'].str.contains("Wasser", case=False, na=False)
    if wasser_mask.any():
        earned.append("b02")
        
    if 'latitude' in df.columns and df['latitude'].notna().any():
        earned.append("b03")
        
    hours = df['Zeitstempel'].dt.hour
    if ((hours >= 17) & (hours < 19)).any():
        earned.append("b04")
        
    if ((hours >= 0) & (hours < 4)).any():
        earned.append("b05")
        
    weekdays = df['Zeitstempel'].dt.dayofweek
    if ((weekdays == 5) | (weekdays == 6)).any():
        earned.append("b06")
        
    # Gefreiter
    if total_drinks >= 10:
        earned.append("b07")
        
    if ((hours >= 6) & (hours < 10)).any():
        earned.append("b08")
        
    # Doppelschlag (2 drinks within 30 mins)
    df['time_diff'] = df['Zeitstempel'].diff()
    if (df['time_diff'] <= pd.Timedelta(minutes=30)).any():
        earned.append("b09")
        
    if (pd.to_numeric(df['Menge_ml'], errors='coerce') == 500).any():
        earned.append("b10")
        
    if (weekdays == 0).any():
        earned.append("b11")
        
    suess_mask = df['Sorte'].str.contains("Cola|Limo|Energy|Sprite|Fanta", case=False, na=False) | df['Marke'].str.contains("Cola|Limo|Energy|Sprite|Fanta", case=False, na=False)
    if suess_mask.any():
        earned.append("b12")
        
    # Unteroffizier
    if total_drinks >= 50:
        earned.append("b13")
        
    unique_dates = df['Zeitstempel'].dt.date.drop_duplicates().sort_values().reset_index(drop=True)
    date_diff = pd.to_datetime(unique_dates).diff().dt.days
    streaks = (date_diff != 1).cumsum()
    max_streak = streaks.value_counts().max() if not streaks.empty else 0
    if max_streak >= 3:
        earned.append("b14")
        
    menge_num = pd.to_numeric(df['Menge_ml'], errors='coerce')
    if (menge_num >= 1000).any():
        earned.append("b15")
        
    alk_num = pd.to_numeric(df['Alk_Vol'], errors='coerce')
    if (alk_num >= 20.0).any():
        earned.append("b16")
        
    shot_mask = df['Sorte'].str.contains("Shot", case=False, na=False) | df['Marke'].str.contains("Shot", case=False, na=False)
    if shot_mask.any():
        earned.append("b17")
        
    if ((weekdays == 6) & (hours >= 6) & (hours < 12)).any():
        earned.append("b18")
        
    # Offizier
    if total_drinks >= 100:
        earned.append("b19")
        
    daily_counts = df.groupby(df['Zeitstempel'].dt.date).size()
    if not daily_counts.empty and daily_counts.max() >= 10:
        earned.append("b20")
        
    if max_streak >= 7:
        earned.append("b21")
        
    if 'latitude' in df.columns:
        gps_df = df[df['latitude'].notna()]
        gps_dates = gps_df['Zeitstempel'].dt.date.nunique()
        if gps_dates >= 3:
            earned.append("b22")
            
    if shot_mask.any():
        shot_daily = df[shot_mask].groupby(df[shot_mask]['Zeitstempel'].dt.date).size()
        if not shot_daily.empty and shot_daily.max() >= 5:
            earned.append("b23")
            
    bier_mask = df['Marke'].str.contains("Brauerei|Bier", case=False, na=False) | df['Sorte'].str.contains("Pils|Helles|Weizen|Bier|Export", case=False, na=False)
    if bier_mask.sum() >= 50:
        earned.append("b24")
        
    # General
    if total_drinks >= 250:
        earned.append("b25")
        
    if total_drinks >= 500:
        earned.append("b26")
        
    if not daily_counts.empty and daily_counts.max() >= 20:
        earned.append("b27")
        
    first_drink = df['Zeitstempel'].min()
    last_drink = df['Zeitstempel'].max()
    if (last_drink - first_drink).days >= 30:
        earned.append("b28")
        
    if df['Zeitstempel'].dt.dayofweek.nunique() == 7:
        earned.append("b29")
        
    if wasser_mask.sum() >= 20:
        earned.append("b30")
        
    return earned

def render_profile_badges(user_badges_list):
    st.markdown("""
        <style>
        .badge-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            text-align: center;
            margin-bottom: 15px;
            padding: 5px;
            position: relative;
            cursor: pointer;
            -webkit-tap-highlight-color: transparent;
        }
        .badge-locked {
            filter: grayscale(100%) opacity(30%);
        }
        .badge-icon {
            font-size: 2.2rem;
            margin-bottom: 5px;
            line-height: 1;
        }
        .badge-name {
            font-size: 0.65rem;
            line-height: 1.1;
        }
        .badge-name-locked {
            color: #888;
            font-size: 0.65rem;
            line-height: 1.1;
        }
        .badge-tooltip {
            visibility: hidden;
            width: 140px;
            background-color: #222;
            color: #fff;
            text-align: center;
            border-radius: 6px;
            padding: 8px;
            position: absolute;
            z-index: 100;
            bottom: 100%;
            left: 50%;
            margin-left: -70px;
            font-size: 0.75rem;
            opacity: 0;
            transition: opacity 0.2s;
            pointer-events: none;
            box-shadow: 0px 4px 6px rgba(0,0,0,0.5);
            margin-bottom: 5px;
        }
        .badge-tooltip::after {
            content: "";
            position: absolute;
            top: 100%;
            left: 50%;
            margin-left: -5px;
            border-width: 5px;
            border-style: solid;
            border-color: #222 transparent transparent transparent;
        }
        .badge-container:hover .badge-tooltip, .badge-container:active .badge-tooltip, .badge-container:focus .badge-tooltip {
            visibility: visible;
            opacity: 1;
        }
        .rank-header {
            font-size: 0.8rem;
            color: #aaa;
            margin-top: 10px;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 1px;
            border-bottom: 1px solid #333;
            padding-bottom: 2px;
        }
        </style>
    """, unsafe_allow_html=True)
    
    ranks = ["Grundausbildung", "Gefreiter", "Unteroffizier", "Offizier", "General"]
    
    for rank in ranks:
        st.markdown(f"<div class='rank-header'>{rank}</div>", unsafe_allow_html=True)
        rank_badges = [b for b in BADGES if b["rank"] == rank]
        
        cols = st.columns(6)
        for i, badge in enumerate(rank_badges):
            col = cols[i % 6]
            is_earned = badge["id"] in user_badges_list
            
            with col:
                if is_earned:
                    st.markdown(f'''
                        <div class="badge-container" tabindex="0">
                            <div class="badge-icon">{badge['icon']}</div>
                            <div class="badge-name"><b>{badge['name']}</b></div>
                            <div class="badge-tooltip">{badge['desc']}</div>
                        </div>
                    ''', unsafe_allow_html=True)
                else:
                    st.markdown(f'''
                        <div class="badge-container" tabindex="0">
                            <div class="badge-icon badge-locked">{badge['icon']}</div>
                            <div class="badge-name-locked">{badge['name']}</div>
                            <div class="badge-tooltip">{badge['desc']}</div>
                        </div>
                    ''', unsafe_allow_html=True)
