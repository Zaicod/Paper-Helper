"""Browser search/CRUD validation using explicitly controlled provider HTTP data.

This validates the three-service integration and real provider parsers, not
availability of the official arXiv/OpenAlex websites.
"""
from vue_smoke import main


if __name__ == '__main__':
    main(search_test=True)
