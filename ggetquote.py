__author__ = 'fernandolourenco'

from googlefinance import getQuotes
import ystockquote

import json
import sqlite3

import datetime
import dateutil.parser
import pytz
#from workalendar.europe import Portugal
import requests

conn = sqlite3.connect('stockdata.sqlite')
conn.row_factory = sqlite3.Row
c = conn.cursor()

for row in c.execute("select * from stocks where tracked='True';"):

    stockid = row["id"]
    stockname = row["name"]

    #see if the stock exchange is opened today

    exchangeid = int(row["exchangeid"])
    c1 = conn.cursor()
    c1.execute("select * from exchanges where id=:id;", {"id":exchangeid})
    exchange = c1.fetchone()
    opendays = exchange["workingdays"].split(",")

    daytoday = str(datetime.datetime.utcnow().weekday())
    datetoday = datetime.datetime.utcnow().strftime("%Y-%m-%d")

    if not(daytoday in opendays): #if stockmarket closed, pass
        print "Stock market %s in weekend for stock %s(%s)" % (exchange['shortnamegoogle'], row["symbolgoogle"],stockname)
        continue

    #see if today is a holliday in the stock exchange
    year = datetime.datetime.utcnow().year
    country = exchange["countrycode"]

    isholliday = False

    #check to see if database knows if this date is holliday
    c2 = conn.cursor()
    c2.execute("select * from hollidays where country=:country and date=:date;", {"country":country, "date":datetoday})
    getholliday = c2.fetchone()
    if getholliday is None: # date is not yet in database for this country
        #check online to see if this date is holliday
        try:
            r = requests.get("http://kayaposoft.com/enrico/json/v1.0/?action=getPublicHolidaysForYear&year=%d&country=%s" % (year, country))
            for date in r.json():
                holliday = datetime.date(date['date']['year'], date['date']['month'], date['date']['day'])
                if datetime.datetime.today() == holliday:
                    isholliday = True
                    break
        except:
            pass

        #save date to database for this country
        c2 = conn.cursor()
        c2.execute("INSERT INTO hollidays(country,date,holliday) VALUES (?,?,?);", (country, datetoday, isholliday)) #save date as holliday
        conn.commit()

    else: # date is allready in database for this country
        isholliday = getholliday['holliday']

    if isholliday: #if today is holliday, pass
        print "Stock market %s in holliday for stock %s(%s)" % (exchange['shortnamegoogle'], row["symbolgoogle"],stockname)
        continue

    #see if the stock exchange is opened now

    now = datetime.datetime.utcnow().replace(tzinfo = pytz.utc) # get current time in UTC with  timezone info
    openhour = exchange["openhour"]
    closehour = exchange["closehour"]

    if not(openhour is None) and not(closehour is None):
        openhour = dateutil.parser.parse(openhour)
        closehour = dateutil.parser.parse(closehour)

        if (now<openhour) or (now>closehour): #if stockmarket closed, pass
            print "Stock market %s closed for stock %s(%s)" % (exchange['shortnamegoogle'], row["symbolgoogle"],stockname)
            continue

    if not(row["lastquotestamp"] is None):
        timestamp = dateutil.parser.parse(row["lastquotestamp"]) # get last quote timestamp and parse into time object
    else:
        timestamp = None
    interval = row["interval"]
    type= row["type"].upper()

    now = datetime.datetime.utcnow() # get current date and time in UTC

    if (timestamp is None) or (now> timestamp + datetime.timedelta(minutes=interval) ): #see if it is time to get a new quote
        if type == "CURRENCY":
            symbol = str(row["symbolyahoo"])
            quote = ystockquote.get_price(symbol) #get quote
        elif type == "STOCK":
            symbol = str(row["symbolgoogle"])
            quote = getQuotes(symbol)[0]["LastTradePrice"]  #get quote

        newtimestamp=datetime.datetime.utcnow().isoformat()+'Z' # all dates saved in UTC iso format
        c1 = conn.cursor()
        c1.execute("UPDATE stocks SET lastquotestamp = ? WHERE ID = ?;",  (newtimestamp, stockid)) #update last quote timestamp
        c1.execute("INSERT INTO quotes(stockid,timestamp,value) VALUES (?,?,?);", (stockid,newtimestamp,quote)) #create new quote
        conn.commit()

        print "Got new stock quote for %s(%s) of %s @%s" % (symbol,stockname,quote,newtimestamp)
