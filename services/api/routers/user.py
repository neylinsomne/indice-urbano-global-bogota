#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# standard python imports

#from werkzeug.security import hmac

from fastapi import APIRouter, Depends
from db.postgre import db_pool

router = APIRouter(prefix="/user", tags=["user","users"])

@router.get("/")
async def read_root():
    async with db_pool.acquire() as connection:
        result = await connection.fetch("SELECT * FROM mi_tabla_geoespacial ORDER BY precio ASC")
        return result



# @router.get("/id")
# class UserModel(db.Model):
#     __tablename__ = 'users'

#     id = db.Column(db.Integer, primary_key=True)
#     username = db.Column(db.String(80))
#     password = db.Column(db.String(80))

#     def __init__(self, username, password):
#         self.username = username
#         self.password = password

#     def save_to_db(self):
#         db.session.add(self)
#         db.session.commit()

#     def check_password(self, password):
#         return hmac.compare_digest(self.password, password)

#     @classmethod
#     def find_by_username(cls, username):
#         return cls.query.filter_by(username=username).first()

#     @classmethod
#     def find_by_id(cls, _id):
#         return cls.query.filter_by(id=_id).first()

