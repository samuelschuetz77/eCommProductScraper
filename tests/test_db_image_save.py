import os
import importlib

import pytest

from app import _save_products_to_db, SessionLocal, Product, ImageURL


def test_save_products_creates_imageurl(monkeypatch, tmp_path):
    # prepare a fake product with an image URL and ensure ImageURL row is created
    product = {
        'name': 'Test Wallet',
        'price': 12.34,
        'image': 'https://example.com/img.jpg',
        'link': 'https://www.walmart.com/ip/1'
    }

    class DummyHead:
        headers = {'Content-Length': '2048'}

    monkeypatch.setattr('requests.head', lambda url, timeout=5: DummyHead())

    # ensure DB schema is up-to-date for the new columns/tables
    from app import Base, engine
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # call save
    saved = _save_products_to_db([product], search_term='wallet-test')
    assert saved and saved[0]['action'] in ('created', 'updated')

    # check DB for ImageURL row
    with SessionLocal() as session:
        p = session.query(Product).filter_by(link=product['link']).first()
        assert p is not None
        imgs = session.query(ImageURL).filter_by(product_id=p.id).all()
        assert len(imgs) == 1
        assert imgs[0].url == product['image']
        assert imgs[0].size_kb == 2  # 2048 bytes -> 2 KB

    # cleanup
    with SessionLocal() as session:
        if p:
            session.query(ImageURL).filter_by(product_id=p.id).delete()
            session.delete(p)
            session.commit()
