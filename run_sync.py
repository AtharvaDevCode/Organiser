from extractor import sync_events_to_db

if __name__ == '__main__':
    print('Starting automated GitHub Actions sync...')
    sync_events_to_db()
    print('Sync finished.')
