# Installed libraries
import tls_client
import apprise

# Standard libraries
import traceback
import datetime
import argparse
import random
import shutil
import time
import json
import csv
import sys
import os


######################## FUNCTIONS ########################

def update_entry_timestamp(file_path, line_number):
    """
    Open the csv file provided and edit the last column of the line number provided
    with the current timestamp.

    Parameters:
    file_path  : The path of the csv file to be editted.
    line_number: The csv line which will be editted.
    """
    current_datetime = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    # Read the CSV file and modify the specific line
    with open(file_path, mode='r', newline='') as file:
        lines = list(csv.reader(file))
        if line_number < 1 or line_number > len(lines):
            raise Exception("index of temp file is out of bounds.")
        lines[line_number][-1] = current_datetime
    # Write the modified data back to the CSV file
    with open(file_path, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerows(lines)

def check_csv_for_old_entries(csv_file, hours):
    """
    Open the csv file provided and check for entries with older timestamp
    than the hours provided. If a timestamp is older that the hours spesified
    then a notification will be sent to telegram.

    Parameters:
    csv_file: The path of the csv file to be checked.
    hours   : The threshold in hours for each entry.
    """
    with open(csv_file, mode='r', newline='') as file:
        reader = csv.DictReader(file)
        for row in reader:
            productName = row['productName']
            # Stop when DISABLED tag is met
            if (productName == "DISABLED"):
                break
            url = row['url']
            # Check if 'last_time_editted' is empty
            if row.get('last_time_editted') is not None and row['last_time_editted'] != '':
                timestamp = datetime.datetime.strptime(row['last_time_editted'], "%d-%m-%Y %H:%M:%S")
                current_time = datetime.datetime.now()
                time_difference = current_time - timestamp
                # Check if an entry has not been updated for a long time
                if time_difference > datetime.timedelta(hours=hours):
                    appNotif.notify(title='Insomnia Check - Attention required!',
                                    body=f'Link {url} has not been updated for {hours} hours.\nCheck if product page has a problem and error logs.')
            else:
                continue

def is_first_sunday_of_the_month(dt):
    """
    Check if the datetime provided is the first sunday of the month.

    Parameters:
    dt: The current datetime.

    Returns:
    bool: True if it is the first sunday of the month, otherwise false.
    """
    # Check if today is Sunday
    if dt.weekday() == 6:
        # Check if it's the first Sunday by seeing if the day is less than or equal to 7
        if dt.day <= 7:
            return True
    return False

def should_send_monthly_notification():
    """
    Check whether a notification should be sent to telegram.
    Only the first sunday of each month a notification should be sent.

    Returns:
    bool: True if it is the first sunday of the month and a notification has not been sent for this month, otherwise false.
    """
    now = datetime.datetime.now()
    # Check if it's the first Sunday and the time is after 09:00
    if is_first_sunday_of_the_month(now) and now.hour >= 9:
        # Check if the file exists and read the month
        if os.path.exists(os.path.join(script_dir, "last_notification_date.txt")):
            with open(os.path.join(script_dir, "last_notification_date.txt"), 'r', newline='') as file:
                last_printed_month = int(file.read().strip())
                # Check if the last printed month is not this month
                if last_printed_month == now.month:
                    return False
        # If it does not exist or the month is different, allow message to be printed
        return True
    return False

def generate_random_number(seconds):
    """
    Generate a random integer number between the 1 and the number of seconds provided.

    Parameters:
    seconds: The upper threshold of the random number generated.

    Returns:
    int: The random number created
    """
    random.seed(time.time())
    return random.randint(1, seconds)

def saveTraceback ():
    """
    In case of an exception save the whole traceback to a log file to review it later.
    The file is named "error_log.txt" and will be available in the root folder of the project.
    Usefull for debugging.
    """
    with open(os.path.join(script_dir, "error_log.txt"), "a", newline='') as log_file:
        time_now = datetime.datetime.now().strftime("%Y-%m-%d (%H:%M:%S)")
        log_file.write(f"\n\nAn error occurred at {time_now}:\n")
        traceback.print_exc(file=log_file)
        log_file.write(f"\n{'-'*100}")

########################### MAIN ###########################

# Apprise configuration
appNotif = apprise.Apprise()
appNotif.add('tgram://<token>/<chat_id>/')

# Project's folders info
script_dir = os.path.dirname(os.path.abspath(__file__))

# Parse "--debug" flag
parser = argparse.ArgumentParser(description='Script with debug flag')
parser.add_argument('--debug', action='store_true', help='Enable debug mode')
args = parser.parse_args()

# Sleep for a random time from 0 to 1 minutes
if not args.debug:
    time.sleep(generate_random_number(60))

# Check if script is already running by another process
if os.path.exists(os.path.join(script_dir, "monitored_products_temp.csv")):
    file_age = time.time() - os.path.getmtime(os.path.join(script_dir, "monitored_products_temp.csv"))
    if file_age > 3000:  # 50 minutes in seconds
        if args.debug:
            print(f"Found stale temp file. Removing it.")
        try:
            os.remove(os.path.join(script_dir, "monitored_products_temp.csv"))
        except OSError:
            pass
    else:
        appNotif.notify(title='Skroutz Check - Attention required!',
                        body='Skroutz Check script did not start! Stale temp file detected. It will be deleted soon.')
        if args.debug:
            print('Skroutz Check script did not start! Stale temp file detected. It will be deleted soon.')
        sys.exit()

try:
    # Create a copy of the product file to maintain open during the execution of the script in read mode.
    shutil.copyfile(os.path.join(script_dir, "monitored_products.csv"), os.path.join(script_dir, "monitored_products_temp.csv"))

    # Open CSV file with monitored products
    with open(os.path.join(script_dir, "monitored_products_temp.csv"), mode='r', newline='') as file:
        check_list = csv.DictReader(file)
        # Main loop
        for index, entry in enumerate(check_list, start=1):
            time.sleep(20 + random.uniform(1, 5))
            productName = entry['productName']
            # Stop when DISABLED tag is met
            if (productName == "DISABLED"):
                break
            url = entry['url']
            # Skip empty csv lines
            if (url == ""):
                continue
            targetPrice = float(entry['targetPrice'])
            # Set the max retries number in case of a connection error
            max_retries = 10
            for attempt in range(max_retries):
                try:
                    headers = {
                        'authority': 'www.skroutz.gr',
                        'accept': 'application/json, text/plain, */*',
                        'accept-language': 'en-US,en;q=0.9',
                        'dnt': '1',
                        'referer': 'https://www.skroutz.gr/search?keyphrase=witcher',
                        'sec-ch-ua': '"Chromium";v="116", "Not)A;Brand";v="24", "Google Chrome";v="116"',
                        'sec-ch-ua-mobile': '?0',
                        'sec-ch-ua-platform': '"Windows"',
                        'sec-fetch-dest': 'empty',
                        'sec-fetch-mode': 'cors',
                        'sec-fetch-site': 'same-origin',
                        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36',
                        'x-requested-with': 'XMLHttpRequest',
                    }
                    session = tls_client.Session(
                        client_identifier="chrome112",
                        random_tls_extension_order=True
                    )
                    # Fetch the product page
                    product_is_available = True
                    idx = url.rindex("/")
                    new_link = url[:idx + 1] + "filter_products.json?"
                    response = session.get(new_link.strip(), headers=headers)
                    response_data = response.json()
                    # Check if the product is available
                    if (response_data["price_min"] is None):
                        current_minimum_price = "-1"
                        product_is_available = False
                    else:
                        current_minimum_price = response_data["price_min"].replace('€', '').replace(",",".")
                    # Skip the rest of the loop if the product is not available
                    if (not product_is_available):
                        if args.debug:
                            print(f"{productName}: Not available")
                        continue
                    # Remove the second dot if it exists (for prices above 1000)
                    if (current_minimum_price.count(".") == 2):
                        current_minimum_price = current_minimum_price.replace(".", "", 1)
                    # Convert the price to float
                    current_minimum_price = float(current_minimum_price)
                    if args.debug:
                        print(f"{productName}: {current_minimum_price} €")
                    # Check if the current price is lower than the target price
                    if (current_minimum_price < targetPrice):
                        appNotif.notify(title='Skroutz Check - Attention required!',
                                        body=f'{productName} found at a price bellow {targetPrice} €.\nCurrent price = {current_minimum_price} €.\nLink: {url}')
                    # Edit timestamp of each entry
                    update_entry_timestamp(os.path.join(script_dir, "monitored_products.csv"), index)
                    # Break the loop of attempts if the process is successful
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
    # Delete temp product file.
    os.remove(os.path.join(script_dir, "monitored_products_temp.csv"))
    # Check for entries that do not update over time.
    check_csv_for_old_entries(os.path.join(script_dir, "monitored_products.csv"), 24)
    # Log Last execution time
    with open(os.path.join(script_dir, "last_time_editted.txt"), "w", newline='') as log_file:
        time_now = datetime.datetime.now().strftime("%Y-%m-%d (%H:%M:%S)")
        log_file.write(f"Last edit --> {time_now}\n")
except Exception:
    saveTraceback()
    appNotif.notify(title='Skroutz Check - Attention required!',
                    body=f'Skroutz Check Script failed. Check error log.')
finally:
    # Delete temp product file if it still exists.
    if os.path.exists(os.path.join(script_dir, "monitored_products_temp.csv")):
        os.remove(os.path.join(script_dir, "monitored_products_temp.csv"))

# Notify user that script is still running every month
if should_send_monthly_notification():
    appNotif.notify(title='Skroutz Check monthly report...', body='Skroutz Check script is still running.')
    with open(os.path.join(script_dir, "last_notification_date.txt"), 'w', newline='') as file:
        file.write(str(datetime.datetime.now().month))
