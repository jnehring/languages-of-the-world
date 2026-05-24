We want to analyse huggingface dataset cards and quantify the state of open-source AI models and datasets for low resource languages.

In a folder ai-language-coverage/src, write the following Python scripts

# Huggingface Downloader

Write a script that downloads all huggingface dataset and model cards.

* it shows a progress bar
* it uses caching to resume the download (in folder .cache/)
* Create these data files
    * data/model_cards.csv with columns type (model or dataset), repo_id and dataset_card (containing the model card)
    * data/metadata.csv contains all metadata such as license, languages, ... parsed from the model cards in 4 columns 
        * type (model / dataset)
        * repo_id
        * key (license, language, ...)
        * value

# Metrics

We want to define metrics to quantify the coverage of AI tooling in different languages. 

* Organize the src/ directory in metrics.
* Create a folder data/metrics that lists the metrics for each language. So, each metric will generate a CSV in this folder.

## Huggingface Metric

Count number of datasets and models from huggingface for each metric.

## Size of wikipedia

Count the number of pages of all wikis from https://meta.wikimedia.org/wiki/List_of_Wikipedias

## Number of pages in common crawl

Fetch the number of websites from the common crawl for each language from this page: https://commoncrawl.github.io/cc-crawl-statistics/plots/languages.csv

# Data analysis

Create notebooks, languages-of-the-world

## Models and datasets per language

creates a table with columns
* language iso639-3
* language label
* number of speakers
* number of ai models
* number of datasets

## Map of the world

* for each country in the world, compute the sum of the numbers of ai tools and datasets
* draw a map of the world and color each country by the number of ai tools and datasets
* draw the same map individually for each continent
