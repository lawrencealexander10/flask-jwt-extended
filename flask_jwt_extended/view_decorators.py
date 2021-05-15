from functools import wraps
from datetime import datetime
from calendar import timegm
from re import split

from werkzeug.exceptions import BadRequest

from flask import request
try:
    from flask import _app_ctx_stack as ctx_stack
except ImportError:  # pragma: no cover
    from flask import _request_ctx_stack as ctx_stack

from flask_jwt_extended.config import config
from flask_jwt_extended.exceptions import (
    CSRFError, FreshTokenRequired, InvalidHeaderError, NoAuthorizationError,
    UserLoadError
)
from flask_jwt_extended.utils import (
    decode_token, has_user_loader, user_loader, verify_token_claims,
    verify_token_not_blacklisted, verify_token_type, get_unverified_jwt_headers
)


async def verify_jwt_in_request():
    """
    Ensure that the requester has a valid access token. This does not check the
    freshness of the access token. Raises an appropiate exception there is
    no token or if the token is invalid.
    """
    if request.method not in config.exempt_methods:
        jwt_data, jwt_header = await _decode_jwt_from_request(request_type='access')
        ctx_stack.top.jwt = jwt_data
        ctx_stack.top.jwt_header = jwt_header
        verify_token_claims(jwt_data)
        _load_user(jwt_data[config.identity_claim_key])


async def verify_jwt_in_request_optional():
    """
    Optionally check if this request has a valid access token.  If an access
    token in present in the request, :func:`~flask_jwt_extended.get_jwt_identity`
    will return  the identity of the access token. If no access token is
    present in the request, this simply returns, and
    :func:`~flask_jwt_extended.get_jwt_identity` will return `None` instead.

    If there is an invalid access token in the request (expired, tampered with,
    etc), this will still raise the appropiate exception.
    """
    try:
        if request.method not in config.exempt_methods:
            jwt_data, jwt_header = await _decode_jwt_from_request(request_type='access')
            ctx_stack.top.jwt = jwt_data
            ctx_stack.top.jwt_header = jwt_header
            verify_token_claims(jwt_data)
            _load_user(jwt_data[config.identity_claim_key])
    except (NoAuthorizationError, InvalidHeaderError):
        pass


async def verify_fresh_jwt_in_request():
    """
    Ensure that the requester has a valid and fresh access token. Raises an
    appropiate exception if there is no token, the token is invalid, or the
    token is not marked as fresh.
    """
    if request.method not in config.exempt_methods:
        jwt_data, jwt_header = await _decode_jwt_from_request(request_type='access')
        ctx_stack.top.jwt = jwt_data
        ctx_stack.top.jwt_header = jwt_header
        fresh = jwt_data['fresh']
        if isinstance(fresh, bool):
            if not fresh:
                raise FreshTokenRequired('Fresh token required')
        else:
            now = timegm(datetime.utcnow().utctimetuple())
            if fresh < now:
                raise FreshTokenRequired('Fresh token required')
        verify_token_claims(jwt_data)
        _load_user(jwt_data[config.identity_claim_key])


async def verify_jwt_refresh_token_in_request ():
    """
    Ensure that the requester has a valid refresh token. Raises an appropiate
    exception if there is no token or the token is invalid.
    """
    if request.method not in config.exempt_methods:
        jwt_data, jwt_header = await _decode_jwt_from_request(request_type='refresh')
        ctx_stack.top.jwt = jwt_data
        ctx_stack.top.jwt_header = jwt_header
        _load_user(jwt_data[config.identity_claim_key])


def jwt_required(fn):
    """
    A decorator to protect a Flask endpoint.

    If you decorate an endpoint with this, it will ensure that the requester
    has a valid access token before allowing the endpoint to be called. This
    does not check the freshness of the access token.

    See also: :func:`~flask_jwt_extended.fresh_jwt_required`
    """
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        await verify_jwt_in_request()
        return fn(*args, **kwargs)
    return wrapper


def async_jwt_required(fn):
    """
    A decorator to protect a Flask endpoint.

    If you decorate an endpoint with this, it will ensure that the requester
    has a valid access token before allowing the endpoint to be called. This
    does not check the freshness of the access token.

    See also: :func:`~flask_jwt_extended.fresh_jwt_required`
    """
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        await verify_jwt_in_request()
        return await fn(*args, **kwargs)
    return wrapper


def jwt_optional(fn):
    """
    A decorator to optionally protect a Flask endpoint

    If an access token in present in the request, this will call the endpoint
    with :func:`~flask_jwt_extended.get_jwt_identity` having the identity
    of the access token. If no access token is present in the request,
    this endpoint will still be called, but
    :func:`~flask_jwt_extended.get_jwt_identity` will return `None` instead.

    If there is an invalid access token in the request (expired, tampered with,
    etc), this will still call the appropriate error handler instead of allowing
    the endpoint to be called as if there is no access token in the request.
    """
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        await verify_jwt_in_request_optional()
        return fn(*args, **kwargs)
    return wrapper


def async_jwt_optional(fn):
    """
    A decorator to optionally protect a Flask endpoint

    If an access token in present in the request, this will call the endpoint
    with :func:`~flask_jwt_extended.get_jwt_identity` having the identity
    of the access token. If no access token is present in the request,
    this endpoint will still be called, but
    :func:`~flask_jwt_extended.get_jwt_identity` will return `None` instead.

    If there is an invalid access token in the request (expired, tampered with,
    etc), this will still call the appropriate error handler instead of allowing
    the endpoint to be called as if there is no access token in the request.
    """
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        await verify_jwt_in_request_optional()
        return await fn(*args, **kwargs)
    return wrapper


def fresh_jwt_required(fn):
    """
    A decorator to protect a Flask endpoint.

    If you decorate an endpoint with this, it will ensure that the requester
    has a valid and fresh access token before allowing the endpoint to be
    called.

    See also: :func:`~flask_jwt_extended.jwt_required`
    """
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        await verify_fresh_jwt_in_request()
        return fn(*args, **kwargs)
    return wrapper


def async_fresh_jwt_required(fn):
    """
    A decorator to protect a Flask endpoint.

    If you decorate an endpoint with this, it will ensure that the requester
    has a valid and fresh access token before allowing the endpoint to be
    called.

    See also: :func:`~flask_jwt_extended.jwt_required`
    """
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        await verify_fresh_jwt_in_request()
        return await fn(*args, **kwargs)
    return wrapper


def jwt_refresh_token_required(fn):
    """
    A decorator to protect a Flask endpoint.

    If you decorate an endpoint with this, it will ensure that the requester
    has a valid refresh token before allowing the endpoint to be called.
    """
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        await verify_jwt_refresh_token_in_request()
        return fn(*args, **kwargs)
    return wrapper


def async_jwt_refresh_token_required(fn):
    """
    A decorator to protect a Flask endpoint.

    If you decorate an endpoint with this, it will ensure that the requester
    has a valid refresh token before allowing the endpoint to be called.
    """
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        await verify_jwt_refresh_token_in_request()
        return await fn(*args, **kwargs)
    return wrapper


def _load_user(identity):
    if has_user_loader():
        user = user_loader(identity)
        if user is None:
            raise UserLoadError("user_loader returned None for {}".format(identity))
        else:
            ctx_stack.top.jwt_user = user


def _decode_jwt_from_headers():
    header_name = config.header_name
    header_type = config.header_type

    # Verify we have the auth header
    auth_header = request.headers.get(header_name, None)
    if not auth_header:
        raise NoAuthorizationError("Missing {} Header".format(header_name))

    # Make sure the header is in a valid format that we are expecting, ie
    # <HeaderName>: <HeaderType(optional)> <JWT>
    jwt_header = None

    # Check if header is comma delimited, ie
    # <HeaderName>: <field> <value>, <field> <value>, etc...
    if header_type:
        field_values = split(r',\s*', auth_header)
        jwt_header = [s for s in field_values if s.split()[0] == header_type]
        if len(jwt_header) < 1 or len(jwt_header[0].split()) != 2:
            msg = "Bad {} header. Expected value '{} <JWT>'".format(
                header_name,
                header_type
            )
            raise InvalidHeaderError(msg)
        jwt_header = jwt_header[0]
    else:
        jwt_header = auth_header

    parts = jwt_header.split()
    if not header_type:
        if len(parts) != 1:
            msg = "Bad {} header. Expected value '<JWT>'".format(header_name)
            raise InvalidHeaderError(msg)
        encoded_token = parts[0]
    else:
        encoded_token = parts[1]

    return encoded_token, None


def _decode_jwt_from_cookies(request_type):
    if request_type == 'access':
        cookie_key = config.access_cookie_name
        csrf_header_key = config.access_csrf_header_name
        csrf_field_key = config.access_csrf_field_name
    else:
        cookie_key = config.refresh_cookie_name
        csrf_header_key = config.refresh_csrf_header_name
        csrf_field_key = config.refresh_csrf_field_name

    encoded_token = request.cookies.get(cookie_key)
    if not encoded_token:
        raise NoAuthorizationError('Missing cookie "{}"'.format(cookie_key))

    if config.csrf_protect and request.method in config.csrf_request_methods:
        csrf_value = request.headers.get(csrf_header_key, None)
        if not csrf_value and config.csrf_check_form:
            csrf_value = request.form.get(csrf_field_key, None)
        if not csrf_value:
            raise CSRFError("Missing CSRF token")
    else:
        csrf_value = None

    return encoded_token, csrf_value


def _decode_jwt_from_query_string():
    query_param = config.query_string_name
    encoded_token = request.args.get(query_param)
    if not encoded_token:
        raise NoAuthorizationError('Missing "{}" query paramater'.format(query_param))

    return encoded_token, None


def _decode_jwt_from_json(request_type):
    if request.content_type != 'application/json':
        raise NoAuthorizationError('Invalid content-type. Must be application/json.')

    if request_type == 'access':
        token_key = config.json_key
    else:
        token_key = config.refresh_json_key

    try:
        encoded_token = request.json.get(token_key, None)
        if not encoded_token:
            raise BadRequest()
    except BadRequest:
        raise NoAuthorizationError('Missing "{}" key in json data.'.format(token_key))

    return encoded_token, None


async def _decode_jwt_from_request(request_type):
    # All the places we can get a JWT from in this request
    get_encoded_token_functions = []

    locations = config.token_location

    # add the functions in the order specified in JWT_TOKEN_LOCATION
    for location in locations:
        if location == 'cookies':
            get_encoded_token_functions.append(
                lambda: _decode_jwt_from_cookies(request_type))
        if location == 'query_string':
            get_encoded_token_functions.append(_decode_jwt_from_query_string)
        if location == 'headers':
            get_encoded_token_functions.append(_decode_jwt_from_headers)
        if location == 'json':
            get_encoded_token_functions.append(
                lambda: _decode_jwt_from_json(request_type))

    # Try to find the token from one of these locations. It only needs to exist
    # in one place to be valid (not every location).
    errors = []
    decoded_token = None
    jwt_header = None
    for get_encoded_token_function in get_encoded_token_functions:
        try:
            encoded_token, csrf_token = get_encoded_token_function()
            decoded_token = decode_token(encoded_token, csrf_token)
            jwt_header = get_unverified_jwt_headers(encoded_token)
            break
        except NoAuthorizationError as e:
            errors.append(str(e))

    # Do some work to make a helpful and human readable error message if no
    # token was found in any of the expected locations.
    if not decoded_token:
        token_locations = config.token_location
        multiple_jwt_locations = len(token_locations) != 1

        if multiple_jwt_locations:
            err_msg = "Missing JWT in {start_locs} or {end_locs} ({details})".format(
                start_locs=", ".join(token_locations[:-1]),
                end_locs=token_locations[-1],
                details="; ".join(errors)
            )
            raise NoAuthorizationError(err_msg)
        else:
            raise NoAuthorizationError(errors[0])

    verify_token_type(decoded_token, expected_type=request_type)
    await verify_token_not_blacklisted(decoded_token, request_type)
    return decoded_token, jwt_header
