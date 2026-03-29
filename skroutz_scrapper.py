# Installed libraries
import tls_client
import apprise
from filelock import FileLock, Timeout

# Standard libraries
import traceback
import datetime
import argparse
import random
import time
import json
import os
import re
from urllib.parse import urlparse


######################## FUNCTIONS ########################

def update_entry_timestamp(file_path, index):
    """
    Open the json file provided and edit the timestamp of the object provided.
    """
    current_datetime = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    with open(file_path, mode='r') as file:
        data = json.load(file)
    if index < 0 or index >= len(data.get("products", [])):
        raise Exception("Index out of bounds.")
    data["products"][index]['last_successful_check'] = current_datetime
    with open(file_path, mode='w') as file:
        json.dump(data, file, indent=2)

def check_json_for_old_entries(json_file, hours, appNotif):
    """
    Open the json file provided and check for entries with older timestamp
    than the hours provided. If a timestamp is older that the hours spesified
    then a notification will be sent to telegram.
    """
    with open(json_file, mode='r') as file:
        data = json.load(file)
        for row in data.get("products", []):
            url = row.get('url', '')
            if row.get('last_successful_check') is not None and row['last_successful_check'] != '':
                timestamp = datetime.datetime.strptime(row['last_successful_check'], "%d-%m-%Y %H:%M:%S")
                current_time = datetime.datetime.now()
                time_difference = current_time - timestamp
                if time_difference > datetime.timedelta(hours=hours):
                    appNotif.notify(title='Skroutz Check - Attention required!',
                                    body=f'Link {url} has not been updated for {hours} hours.\nCheck if product page has a problem and error logs.')

def is_first_sunday_of_the_month(dt):
    if dt.weekday() == 6:
        if dt.day <= 7:
            return True
    return False

def should_send_monthly_notification(script_dir):
    now = datetime.datetime.now()
    if is_first_sunday_of_the_month(now) and now.hour >= 9:
        if os.path.exists(os.path.join(script_dir, "last_notification_date.txt")):
            with open(os.path.join(script_dir, "last_notification_date.txt"), 'r', newline='') as file:
                last_printed_month = int(file.read().strip())
                if last_printed_month == now.month:
                    return False
        return True
    return False

def generate_random_number(seconds):
    random.seed(time.time())
    return random.randint(1, seconds)

def saveTraceback(script_dir):
    with open(os.path.join(script_dir, "error_log.txt"), "a", newline='') as log_file:
        time_now = datetime.datetime.now().strftime("%Y-%m-%d (%H:%M:%S)")
        log_file.write(f"\n\nAn error occurred at {time_now}:\n")
        traceback.print_exc(file=log_file)
        log_file.write(f"\n{'-'*100}")

########################### MAIN ###########################

script_dir = os.path.dirname(os.path.abspath(__file__))

json_file_path = os.path.join(script_dir, "monitored_products.json")
telegram_url = ""
if os.path.exists(json_file_path):
    with open(json_file_path, 'r') as file:
        config_data = json.load(file)
        telegram_url = config_data.get("credentials", {}).get("telegram", "")

appNotif = apprise.Apprise()
if telegram_url:
    appNotif.add(telegram_url)

parser = argparse.ArgumentParser(description='Script with debug flag')
parser.add_argument('--debug', action='store_true', help='Enable debug mode')
args = parser.parse_args()

if not args.debug:
    time.sleep(generate_random_number(60))

lock_file_path = os.path.join(script_dir, "skroutz_check.lock")
lock = FileLock(lock_file_path, timeout=0)

try:
    with lock:
        with open(os.path.join(script_dir, "monitored_products.json"), mode='r') as file:
            config_data = json.load(file)
            check_list = config_data.get("products", [])
        
        for index, entry in enumerate(check_list):
            time.sleep(20 + random.uniform(1, 5))
            productName = entry['productName']
            url = entry['url']
            if (url == ""):
                continue
            targetPrice = float(entry['targetPrice'])
            max_retries = 10
            for attempt in range(max_retries):
                try:
                    headers = {
                        'authority': 'www.skroutz.gr',
                        'accept': 'application/json, text/plain, */*',
                        'accept-language': 'en-US,en;q=0.9',
                        'dnt': '1',
                        'referer': 'https://www.skroutz.gr/search?keyphrase=witcher',
                        'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                        'sec-ch-ua-mobile': '?0',
                        'sec-ch-ua-platform': '"Windows"',
                        'sec-fetch-dest': 'empty',
                        'sec-fetch-mode': 'cors',
                        'sec-fetch-site': 'same-origin',
                        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                        'x-requested-with': 'XMLHttpRequest',
                    }
                    session = tls_client.Session(
                        client_identifier="chrome120",
                        random_tls_extension_order=True
                    )
                    product_is_available = True
                    
                    parsed_url = urlparse(url)
                    match = re.search(r'/s/(\d+)', parsed_url.path)
                    
                    if not match:
                        if args.debug:
                            print(f"{productName}: Failed to parse product ID from URL: {url}")
                        session.close()
                        break
                        
                    product_id = match.group(1)
                    new_link = f"https://www.skroutz.gr/s/{product_id}/filter_products.json?"
                    
                    response = session.get(new_link.strip(), headers=headers)
                    response_data = response.json()
                    if (response_data["price_min"] is None):
                        current_minimum_price = "-1"
                        product_is_available = False
                    else:
                        current_minimum_price = response_data["price_min"].replace('€', '').replace(",",".")
                    if (not product_is_available):
                        if args.debug:
                            print(f"{productName}: Not available")
                        continue
                    if (current_minimum_price.count(".") == 2):
                        current_minimum_price = current_minimum_price.replace(".", "", 1)
                    current_minimum_price = float(current_minimum_price)
                    if args.debug:
                        print(f"{productName}: {current_minimum_price} €")
                    if (current_minimum_price < targetPrice):
                        appNotif.notify(title='Skroutz Check - Attention required!',
                                        body=f'{productName} found at a price bellow {targetPrice} €.\nCurrent price = {current_minimum_price} €.\nLink: {url}')
                    update_entry_timestamp(os.path.join(script_dir, "monitored_products.json"), index)
                    session.close()
                    break
                except json.JSONDecodeError as e:
                    if args.debug:
                        print(f"Attempt {attempt + 1} failed: Received empty response from site.")
                    session.close()
                    time.sleep(20 + (3 * attempt) + random.uniform(1, 5))
                except Exception:
                    if args.debug:
                        print(f'FAILED (Exception) --> {productName} --> {url}')
                    session.close()
                    raise
        check_json_for_old_entries(os.path.join(script_dir, "monitored_products.json"), 24, appNotif)
except Timeout:
    # A lock could not be acquired because another instance is already running
    if args.debug:
        print('Skroutz Check script did not start! Another instance is currently running.')
except Exception:
    saveTraceback(script_dir)
    appNotif.notify(title='Skroutz Check - Attention required!',
                    body=f'Skroutz Check Script failed. Check error log.')

if should_send_monthly_notification(script_dir):
    appNotif.notify(title='Skroutz Check monthly report...', body='Skroutz Check script is still running.')
    with open(os.path.join(script_dir, "last_notification_date.txt"), 'w', newline='') as file:
        file.write(str(datetime.datetime.now().month))
