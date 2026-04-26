# BHRC Human Rights Controversy Dataset – STOXX Europe 600

This project automatically collects human rights allegations, lawsuits, and attacks on human rights defenders involving companies in the STOXX Europe 600 (as of August 2025). It retrieves the number of controversies, the year they happened, and the original URL from the Business & Human Rights Resource Centre (BHRC).

The final output is a structured longitudinal panel dataset ready for use in research. The goal is to make the data collection process more reproducible and easier to update over time, instead of collecting everything manually each year.

This dataset was originally built to support my master’s thesis on whether ESG ratings capture human rights performance. The first version was done manually, while this project automates and structures the process.


## 1. Methodology

Because of how BHRC is structured, company names and company profile URLs first had to be collected manually. This was necessary because BHRC does not use identifiers such as ISIN or RIC, and company names on the website are often inconsistent or different from financial market identifiers.

Starting from these manually matched BHRC URLs, the script first retrieves the BHRC company ID assigned to each firm. Using this ID, it then collects controversy records for three categories:

- Human rights defender attacks (HRD attacks)
- Lawsuits
- Other allegations

The data is then cleaned, deduplicated, and transformed into an analysis-ready panel dataset.


## 2. How to Run

First, install the required packages:

```bash
pip install -r requirements.txt
```

Then run the two scripts in order:

```bash
python 01_collect_bhrc_data.py
python 02_build_panel_dataset.py
```

The first script collects and cleans the BHRC controversy records.

The second script transforms the cleaned event-level data into a company-category-year panel dataset.

The first script requires an input file containing the manually matched STOXX Europe 600 companies and their corresponding BHRC company profile URLs (`stoxx_bhrc_company_mapping.csv`).

This manual mapping step is necessary because BHRC does not use financial identifiers such as ISIN or RIC, and company names on the website are often inconsistent.

The outputs are automatically saved in the `data/output/` folder.


## 3. Outputs

There are three main outputs:

- **company_ids.csv**

Mapping between STOXX Europe 600 firms and BHRC company IDs for matched firms. This makes it possible to verify which firms were successfully matched.

- **events_clean.csv**

Cleaned event-level dataset containing controversy records by company, category, date, and source URL.

- **panel_by_company_category_year.csv**

Final analysis-ready panel dataset with yearly controversy counts by company and category (HRD attacks, lawsuits, and other allegations), including zero values for firms with no recorded events.


## 4. Limitations

- New firms must be manually added to the input mapping file before scraping if they are added to the BHRC website

- Out of 600 STOXX Europe 600 firms, only 408 could be matched to a BHRC company profile

- BHRC’s definition of human rights allegations is not always fully clear, and some cases may also be considered environmental controversies

- Coverage is likely influenced by firm visibility and media attention since BHRC relies on public reporting from NGOs, media, and legal sources

- Some overlap may exist between categories such as lawsuits, HRD attacks, and other allegations despite cleaning procedures


## 5. Next Steps

- Extend the dataset to S&P 500 firms (August 2025 constituents)

- Compare controversy patterns between STOXX Europe 600 and S&P 500 firms
