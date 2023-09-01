# this is a god forsaken language

# "im too good for high level languages"
# ~nisan 2023

# "i dont know"
# ~zidanni 2023

from flask import Flask, render_template, request
from flask_mail import Mail, Message
import argparse
import ctypes
import sys 
import datetime
import platform
import os
import re
import json
import mysql.connector

app = Flask(__name__)

WORDS = []
found_separator = False
email_sent_for_current_entry = False

# obviously replace everything with real creds.
db_config = {
    'host':     '0.0.0.0',
    'user':     'guest',
    'password': 'password',
    'database': 'database'
}

# replace with real creds.
app.config['MAIL_SERVER']   = 'smtp.gmail.com' 
app.config['MAIL_PORT']     = 587  
app.config['MAIL_USE_TLS']  = True  
app.config['MAIL_USERNAME'] = 'username@gmail.com' 
app.config['MAIL_PASSWORD'] = 'password'           

latest_processed_datetime = None

mail = Mail(app)

def database_insert(data):
    try:
        db_connection = mysql.connector.connect(**db_config)
        db_cursor = db_connection.cursor()

        select_query = "SELECT Datetime, Door, Status, CardNumber FROM Data WHERE Datetime = %s AND Door = %s AND Status = %s AND CardNumber = %s"
        insert_query = "INSERT INTO Data (Datetime, Door, Status, CardNumber) VALUES (%s, %s, %s, %s)" 
        
        for entry in data:
            values = (entry['Read Date'], entry['Addr'], entry['Status'], entry['Card No'])
            
            db_cursor.execute(select_query, values)
            existing_entry = db_cursor.fetchone()

            if not existing_entry:
                db_cursor.execute(insert_query, values)
        
        db_connection.commit()
        db_connection.close()
    except Exception as e:
        print("Error inserting data:", str(e))

def jsonify(file_path):
    file = open(file_path, "r")
    data = file.read()
    file.close()

    pattern = r"(\d{4}-\d{2}-\d{2} \d{2}-\d{2}-\d{2}\.\d+).*?Card NO:\s+(.*?)\n.*?Read Date:\s+(.*?)\n.*?Addr:\s+(.*?)\n.*?Status:\s+(.*?)\n"

    entries = re.findall(pattern, data, re.DOTALL)

    cards_data = []
    for entry in entries:
        read_date, card_no, read_date_card, addr, status = entry
        cards_data.append({
            'Read Date': read_date_card,
            'Addr': addr,
            'Status': status,
            'Card No': card_no
        })

    cards_data_str = json.dumps(cards_data, indent=4)
    return cards_data_str

def read_blacklisted_cards():
    try:
        with open('blacklisted_cards.json', 'r') as json_file:
            blacklisted_data = json.load(json_file)
            return blacklisted_data
    except FileNotFoundError:
        return {"error": "File not found"}, 404

@app.route('/send_email')
def send_email(card_number, address):
    blacklisted_data = read_blacklisted_cards()

    try:
        msg = Message(
            'Wanderguard Detected',
            sender=app.config['MAIL_USERNAME'],
            recipients=['username@gmail.com'] # change later
        )
        for card in blacklisted_data['blacklisted_card_numbers']:
            if card == card_number:
                cardIndex = blacklisted_data['blacklisted_card_numbers'].index(card)
            
        msg.body = "Alert: Blacklisted card number {} detected at address {} with owner {}".format(card_number, address, blacklisted_data['blacklisted_card_owners'][cardIndex])
        mail.send(msg)
        return "Email sent!"
    except Exception as e:
        return f"Error sending email: {str(e)}"

previous_blacklisted_data = set()

@app.route("/get_latest_data")
def get_latest_data():
    global latest_processed_datetime
    
    log_data = jsonify("../../AccessControl/n3k_log.log") 
    log_data_json = json.loads(log_data)
    latest_entry = log_data_json[-1]

    blacklisted_data = read_blacklisted_cards().get("blacklisted_card_numbers", [])

    database_insert(log_data_json)

    db_connection = mysql.connector.connect(**db_config)
    db_cursor = db_connection.cursor()
    db_cursor.execute('SELECT Datetime, Door, Status, CardNumber FROM Data ORDER BY Datetime DESC  LIMIT 50') #i have a love / hate relationship with SQL
    data = db_cursor.fetchall()
    
    if data:
        db_latest_entry_datetime = data[0][0]  

        if db_latest_entry_datetime != latest_processed_datetime and latest_entry['Card No'] in blacklisted_data and latest_entry['Status'] == "Denied Access:No PRIVILEGE":
            send_email(latest_entry['Card No'], latest_entry['Addr'],)
            latest_processed_datetime = db_latest_entry_datetime 
    
    db_cursor.close()
    
    return json.dumps(data)

@app.route('/get_blacklisted_cards')
def get_blacklisted_cards():
    return read_blacklisted_cards()

@app.route('/add_blacklisted_card', methods=['POST'])
def add_blacklisted_card():
    try:
        card_number = request.form.get('card_number', '').strip()
        card_owner = request.form.get('card_owner', '').strip()
        if card_number:
            blacklisted_data = read_blacklisted_cards()
            blacklisted_card_numbers = blacklisted_data.get('blacklisted_card_numbers', [])
            blacklisted_card_owners = blacklisted_data.get('blacklisted_card_owners', [])

            if card_number not in blacklisted_card_numbers and card_owner not in blacklisted_card_owners:
                blacklisted_card_numbers.append(card_number)
                blacklisted_card_owners.append(card_owner)
                blacklisted_data['blacklisted_card_numbers'] = blacklisted_card_numbers
                blacklisted_data['blacklisted_card_owners'] = blacklisted_card_owners

                with open('blacklisted_cards.json', 'w') as json_file:
                    json.dump(blacklisted_data, json_file, indent=4)
                    
                return "Card added to the blacklist successfully!"
            else:
                return "Card is already blacklisted."
        else:
            return "Invalid card number."
    except Exception as e:
        return f"Error adding card: {str(e)}"

@app.route('/remove_blacklisted_card', methods=['POST'])
def remove_blacklisted_card():
    try:
        data = request.get_json()
        card_number = data.get('card_number', '').strip()
        card_owner = data.get('card_owner', '').strip()
        
        if card_number:
            blacklisted_data = read_blacklisted_cards()
            blacklisted_card_numbers = blacklisted_data.get('blacklisted_card_numbers', [])
            blacklisted_card_owners = blacklisted_data.get('blacklisted_card_owners', [])

            if card_number in blacklisted_card_numbers and card_owner in blacklisted_card_owners:
                blacklisted_card_numbers.remove(card_number)
                blacklisted_card_owners.remove(card_owner)
                blacklisted_data['blacklisted_card_numbers'] = blacklisted_card_numbers
                blacklisted_data['blacklisted_card_owners'] = blacklisted_card_owners

                with open('blacklisted_cards.json', 'w') as json_file:
                    json.dump(blacklisted_data, json_file, indent=4)
                    
                return "Card removed from the blacklist successfully!"
            else:
                return "Card number is not in the blacklist."
        else:
            return "Invalid card number."
    except Exception as e:
        return f"Error removing card: {str(e)}"

@app.route("/monitor_card", methods=["GET", "POST"])
def monitor_card():
    if request.method == "POST":
        card_number = request.form.get("card_number")
        if card_number:
            alerts = fetch_alerts(card_number)
            return render_template("monitor_card.html", card_number=card_number, alerts=alerts)
        else:
            return "Invalid card number."
    
    return render_template("monitor_card.html")

def fetch_alerts(card_number):
    try:
        blacklisted_data = read_blacklisted_cards()
        blacklisted_card_numbers = blacklisted_data.get('blacklisted_card_numbers', [])
        cards = card_number.split(',')

        db_connection = mysql.connector.connect(**db_config)
        db_cursor = db_connection.cursor()
        cardCommand = ""
        for card in cards:
             if (card != cards[-1]):
                cardCommand += card + " OR CardNumber =" 
             else:
                 cardCommand += card
        query = "SELECT Datetime, Door, Status, CardNumber FROM Data WHERE CardNumber = " + cardCommand +" ORDER BY Datetime DESC"
        db_cursor.execute(query)
        alerts = db_cursor.fetchall()
        db_cursor.close()

        return alerts
    except Exception as e:
        return None

@app.route("/get_alerts/<card_number>")
def get_alerts(card_number):
    try:
        blacklisted_data = read_blacklisted_cards()
        blacklisted_card_numbers = blacklisted_data.get('blacklisted_card_numbers', [])

        cards = card_number.split(',')

        db_connection = mysql.connector.connect(**db_config)
        db_cursor = db_connection.cursor()

        cardCommand = ""
        for card in cards:
             if (card != cards[-1]):
                cardCommand += card + " OR CardNumber =" 
             else:
                 cardCommand += card
        query = "SELECT Datetime, Door, Status, CardNumber FROM Data WHERE CardNumber = " + cardCommand +" ORDER BY Datetime DESC"
        print(query)
        db_cursor.execute(query)
        alerts = db_cursor.fetchall()
        db_cursor.close()

        return json.dumps(alerts)
    except Exception as e:
        return "Error fetching alerts: " + str(e)

@app.route("/add_card")
def add_card_page():
    return render_template("add_card.html")

@app.route("/")
def home():
    return render_template("template.html")

if __name__ == "__main__":
    app.run()
