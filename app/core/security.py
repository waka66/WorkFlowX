#用户密码加密
from passlib.context import CryptContext

# bcrypt自动加盐，推荐
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 明文密码 → 哈希密文（注册用）
def get_password_hash(plain_pwd: str) -> str:
    return pwd_context.hash(plain_pwd)

def verify_password(plain_pwd: str, hashed_pwd: str) -> bool:
    return pwd_context.verify(plain_pwd, hashed_pwd)

print(get_password_hash("Admin@123456"))

#--------------------------------------------------------------------------------------------------------
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from app.models.user import User
from app.core.exceptions import UnauthorizedError
import logging


logger = logging.getLogger("app.core.security")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

#生成密钥的方法，终端输入：openssl rand -hex 32
SECRET_KEY = "c9eacb031e2c6e28a73439ec449910f1bd25c1cfd5eb9b7d85dd88842d03d8de"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # 过期时间30分钟

#生成token
def create_user_access_token(user: User):
    expires_in = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    expire_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)#设置token的过期时间
    to_encode = {
        "sub": str(user.id),
        "exp": expire_at
    }
    encoded_jwt = jwt.encode(
        to_encode,            #通过token传输的内容
        SECRET_KEY,           #jwt签名的密钥
        algorithm=ALGORITHM,  #加密算法
    )
    return encoded_jwt,expires_in


#验证token
def get_user_access_token(token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        return payload
    except ExpiredSignatureError:   # Token过期
        raise UnauthorizedError(code="TOKEN_EXPIRED",message="Token已过期")
    except InvalidTokenError as e:       # Token无效
        logger.warning(f"JWT验证失败: {e}")
        raise UnauthorizedError(code="INVALID_ACCESS_TOKEN",message="无效的访问令牌")

#-----------------------------------------------------------------------------------------------------
import secrets
import hashlib

REFRESH_TOKEN_EXPIRE_DAYS = 7

def create_refresh_token_hash() -> str:
    refresh_token = secrets.token_urlsafe(32)
    refresh_token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    expire_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return refresh_token, refresh_token_hash, expire_at
















