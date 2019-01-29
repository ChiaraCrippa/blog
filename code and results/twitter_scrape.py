#!/usr/bin/env python

import argparse
import json
import os
import requests # libreria che permette di fare richieste in 'http' quindi per prendere l'URL
import shutil
import multiprocessing
import logging
import time

logger = logging.getLogger("scraper")
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)
logger.setLevel(logging.DEBUG)

from iso3166 import countries # libreria che permette di passare da codice iso dei Paesi al corrispettivo nome esteso
from retrying import retry
from selenium import webdriver # libreria che permette di interagire con chrome
from selenium.webdriver.common.keys import Keys
from urllib.parse import quote # libreria che permette di gestire gli spazzi nell'URL

# funzione per riprovare il download delle immagini fallite al più 3 volte
@retry(wait_exponential_multiplier=1000, wait_exponential_max=10000, stop_max_attempt_number=3)
def download_image(url, dst):
	try:
		r = requests.get(url, stream=True, timeout=3)
		r.raise_for_status
	except Exception as e:
		logger.warning(f"Download error: {e}")
		raise e # identificare eccezione per permettere al '@retry' di riprovare il download
	logger.debug(f"Downloading {url} to {dst}")
	with open(dst, 'wb+') as f:
		r.raw.decode_content = True # dato che si salvano immagini è richiesto il formato binario
		shutil.copyfileobj(r.raw, f)
        
# definizione della classe mediante costruttore _init_ per istanziare un oggetto di tipo TwitterMediaScraper() a cui si passano gli oggetti che si vogliono contenere.
class TwitterMediaScraper():
	def __init__(self, countries, samples, save_path):
		self.countries = countries
		self.samples = samples
		self.save_path = save_path # cartella dove salvare i risultati
		self.results = {} # variabile che l'oggetto utilizza per tenere traccia dei risultati
        
# creazione del metodo _build_query() per permettere di passare le diverse countries popolando la stringa con i parametri corretti.
	def _build_query(self, country):
		full_name = quote(countries.get(country).name) 
		return f"filter%3Aimages%20near%3A%22{full_name}%22%20within%3A500mi%20since%3A2018-12-31%20until%3A2019-01-02&src=typd&lang={country}"

# metodo _get_media_urls() che interfaccia con chrome attraverso la modalità 'headless'.
	def _get_media_urls(self, country):
		logger.info(f"Getting urls for country {country}")
		logger.debug(f"Starting chrome headless browser")
        # dichiarazione della modalità di interfaccia di chrome per maggiore efficienza
		options = webdriver.ChromeOptions()
		options.add_argument('headless')
        # istanziare il browser
		browser = webdriver.Chrome(options=options)
		url = "https://twitter.com/search?q=" + self._build_query(country)
        # accedere al determinato URL
		browser.get(url)
		# dare il tempo alla pagina di caricare
		time.sleep(1)
        # accedere al 'body' di interesse (in HTML) nella pagina
		body = browser.find_element_by_tag_name('body')
		def send_keydown():
			logger.debug("Sending keydown events")
            # creo funzione send_keys() sul 'body' per scrollare la pagina in maniera da avere più tweet
			for _ in range(100):
				body.send_keys(Keys.PAGE_DOWN)
				time.sleep(0.2)
        # chiamare prima volta funzione        
		send_keydown()
        # cercare l'elemento 'js-adaptive-photo' dove sono contenute anche le immagini
		page_tweets = browser.find_elements_by_class_name('js-adaptive-photo')  
		logger.info(f"Found {len(page_tweets)} tweets")
        # last_run inizializzato a zero per comprendere possibili stop nel loop
		last_run = 0
        # loop di al più 1000 elementi
		while len(page_tweets) < self.samples:
			page_tweets = []
			send_keydown()
			page_tweets = browser.find_elements_by_class_name('js-adaptive-photo')
			if last_run == len(page_tweets):
				# avviso di blocco perchè si sono scrollato tutti i tweet (=100) nella pagina
				logger.warning(f"Stuck at {len(page_tweets)} for {country}, saving what we got ...")
				break
			last_run = len(page_tweets)
			logger.info(f"Found {len(page_tweets)} tweets")

# considerare immagini 'unique' mediante funzione map() per ogni elemento della lista
		uniq = set(map(lambda t: t.get_attribute("data-image-url"), page_tweets))
		logger.info(f"Found {len(uniq)} uniqe images")
		ret = list(uniq)[:self.samples]
		logger.debug(f"Returning {len(ret)} images")
		browser.quit()
		return ret
    
# funzione per salvare le immagini
	def _save_images(self, country):
		logger.info(f"Downloading images for country {country}")
		country_path = os.path.join(self.save_path, country)
        # creazione cartella per ogni Paese per contenere lista URL
		os.makedirs(country_path, exist_ok=True)
		urls_path = os.path.join(country_path, "urls")
		logger.debug(f"Saving urls in {urls_path}")
		urls = self.results[country]
		logger.debug(f"Saving urls for country {country}")
		with open(urls_path, 'w+') as f:
			f.write('\n'.join(urls))
		chunk_size = 100
		for i in range(0, len(urls), chunk_size):
			chunk = urls[i:i + chunk_size]
			logger.debug(f"Fetching {len(chunk)} images for {country}")
			jobs = []
			for url in chunk:
				dst = os.path.join(country_path, url.split('/')[-1]) # costruzione del path
				p = multiprocessing.Process(target=download_image, args=(url,dst,)) 
				jobs.append(p)
				p.start() # processo per scaricare in parallelo 100 immagini alla volta
			for j in jobs:
				j.join()
			logger.debug("Sleeping 10s to avoid throttling")
			time.sleep(10)

# metodo run() che abilita tutti gli altri metodi. Mediante loop itera sulle variabili countries e salva i risultati del metodo _get_media_urls() in un dizionario.Questo metodo controlla se dry_run() è stato correttamente passato. In questo caso salva l'immagine nella cartella del Paese corrispondente, altrimenti non stampa l'immagine.
	def run(self, dry_run=False):
		for country in self.countries:
			self.results[country] = self._get_media_urls(country)
			if not dry_run:
				self._save_images(country)
		if dry_run:
			print(self.results)
            
# creazione del metodo TwitterMediaScraper()           
def cli():
	parser = argparse.ArgumentParser()
	parser.add_argument('-c', '--countries', nargs='+', help='List of contries eg: USA IT ...', required=True)
	parser.add_argument('-s', '--samples', type=int, help='Number of samples per country', required=True)
	parser.add_argument('-d', '--dry_run', action='store_true', help='Dry run, print results only, do not download')
	parser.add_argument('-p', '--path', type=str, default=".", help='Path where to download imagess, defaults to local dir')
	args = parser.parse_args()
	tw_scraper = TwitterMediaScraper(args.countries, args.samples,args.path)
	tw_scraper.run(dry_run=args.dry_run) # serve per evitare di scaricare i risultati
    
# main del programma che permette di attivare funzione cli()
if __name__ == "__main__":
	cli()
