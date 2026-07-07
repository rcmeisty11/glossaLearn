from flask import request, jsonify, Blueprint
import requests
import os
import json
import psycopg
import datetime
import os
import pprint

from flask import Flask, jsonify, request, render_template, url_for, redirect, make_response
from werkzeug.exceptions import Forbidden
from tempfile import mkdtemp

from flask import Flask, request, jsonify, send_file, g
from flask_caching import Cache
from pylti1p3.contrib.flask import FlaskOIDCLogin, FlaskMessageLaunch, FlaskRequest, FlaskCacheDataStorage
from pylti1p3.deep_link_resource import DeepLinkResource
from pylti1p3.grade import Grade
from pylti1p3.lineitem import LineItem
from pylti1p3.tool_config import ToolConfJsonFile, ToolConfDict
from pylti1p3.registration import Registration
from pylti1p3.exception import LtiException
from urllib.parse import quote, unquote
from flask import abort

from pylti1p3.assignments_grades import AssignmentsGradesService

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@lti-postgres:5432/app_db"
)

DEPLOYMENT_URL = os.getenv(
    "DEPLOYMENT_URL",
    "http://localhost:5173"
)

def get_connection():
    conn = None
    try:
        conn = psycopg.connect(DATABASE_URL)
    except Exception as e:
        print(f"Failed to connect to db at {DATABASE_URL}")
        abort(500)
    return conn
        

# BUG(UPSTREAM): MONKEYPATCH: for some reason we are getting http:// links for lineitems, seemingly not affecting other services
_original_init = AssignmentsGradesService.__init__
def patched_init(self, service_connector, service_data):
    _original_init(self, service_connector, service_data)
    self._service_data["lineitems"] = self._service_data["lineitems"].replace("http://", "https://")

AssignmentsGradesService.__init__ = patched_init

TOOL_CONFIG_MANUAL = {
    "https://glossalearn.link": [{
        
        "client_id": "10000000000005",

        "auth_login_url": "https://glossalearn.link/api/lti/authorize_redirect",
        "auth_token_url": "https://glossalearn.link/login/oauth2/token",
        "key_set_url": "https://glossalearn.link/api/lti/security/jwks",
        
        "default": False,
        "key_set": None,
        "private_key_file": "private.key",
        "public_key_file": "public.key",
    }]
}

PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAuvEnCaUOy1l9gk3wjW3P
ib1dBc5g92+6rhvZZOsN1a77fdOqKsrjWG1lDu8kq2nL+wbAzR3DdEPVw/1WUwtr
/Q1d5m+7S4ciXT63pENs1EPwWmeN33O0zkGx8I7vdiOTSVoywEyUZe6UyS+ujLfs
Rc2ImeLP5OHxpE1yULEDSiMLtSvgzEaMvf2AkVq5EL5nLYDWXZWXUnpiT/f7iK47
Mp2iQd4KYYG7YZ7lMMPCMBuhej7SOtZQ2FwaBjvZiXDZ172sQYBCiBAmOR3ofTL6
aD2+HUxYztVIPCkhyO84mQ7W4BFsOnKW4WRfEySHXd2hZkFMgcFNXY3dA6de519q
lcrL0YYx8ZHpzNt0foEzUsgJd8uJMUVvzPZgExwcyIbv5jWYBg0ILgULo7ve7VXG
5lMwasW/ch2zKp7tTILnDJwITMjF71h4fn4dMTun/7MWEtSl/iFiALnIL/4/YY71
7cr4rmcG1424LyxJGRD9L9WjO8etAbPkiRFJUd5fmfqjHkO6fPxyWsMUAu8bfYdV
RH7qN/erfGHmykmVGgH8AfK9GLT/cjN4GHA29bK9jMed6SWdrkygbQmlnsCAHrw0
RA+QE0t617h3uTrSEr5vkbLz+KThVEBfH84qsweqcac/unKIZ0e2iRuyVnG4cbq8
HUdio8gJ62D3wZ0UvVgr4a0CAwEAAQ==
-----END PUBLIC KEY-----"""

PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
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
-----END RSA PRIVATE KEY-----"""

# upon adding a course, generate some keys so we don't need to depend on the keys
def get_private_public_keys():
    # TODO: randomly generate these
    return (PRIVATE_KEY, PUBLIC_KEY)
    

def get_configs_from_db():
    return TOOL_CONFIG_MANUAL

def insert_deployment_info(deployment_url, client_id, auth_login_url, auth_token_url, key_set_url):
    query = """
            INSERT INTO deployment_info (
                deployment_url, client_id, auth_login_url, auth_token_url, key_set_url
            )
            VALUES (
                %s, %s, %s, %s, %s
            )
            ON CONFLICT(deployment_url, client_id) DO UPDATE
            SET auth_login_url = EXCLUDED.auth_login_url,
            auth_token_url = EXCLUDED.auth_token_url,
            key_set_url = EXCLUDED.key_set_url
            RETURNING 1 ;
        """

    values = (
        deployment_url, client_id, auth_login_url, auth_token_url, key_set_url
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, values)
            cur.fetchone()

        conn.commit()

def insert_course(deployment_url, client_id, deployment_id):
    query = """
            INSERT INTO course (
                deployment_url, client_id, deployment_id
            )
            VALUES (
                %s, %s, %s
            )
            ON CONFLICT(deployment_url, deployment_id) DO UPDATE
            SET client_id = EXCLUDED.client_id
            RETURNING 1 ;
        """

    values = (
        deployment_url, client_id, deployment_id
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, values)
            cur.fetchone()

        conn.commit()

def get_deployment_info(deployment_url, client_id):
    query = """
        SELECT
            deployment_url, client_id, auth_login_url, auth_token_url, key_set_url
        FROM deployment_info
        WHERE deployment_url = %s AND client_id = %s;
    """
    res = None

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (deployment_url,client_id))
            rows = cur.fetchall()


            for row in rows:
                res = {
                    "deployment_url": row[0],
                    "client_id": row[1],
                    "auth_login_url": row[2],
                    "auth_token_url": row[3],
                    "key_set_url": row[4]
                }

    return res
def get_course(deployment_url, deployment_id):
    query = """
        SELECT
            deployment_url, client_id, deployment_id
        FROM course
        WHERE deployment_url = %s AND deployment_id = %s;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (deployment_url,deployment_id))
            rows = cur.fetchall()

    res = None

    for row in rows:
        res = {
            "deployment_url": row[0],
            "client_id": row[1],
            "deployment_id": row[2]
        }

    return res

# TODO: UI should specify deployment_url, deployment_id to be unbroken
def get_tool_config(deployment_url, deployment_id):
    # configs = {
    #     "https://glossalearn.link": [{
            
    #         "client_id": "10000000000005",

    #         "auth_login_url": "https://glossalearn.link/api/lti/authorize_redirect",
    #         "auth_token_url": "https://glossalearn.link/login/oauth2/token",
    #         "key_set_url": "https://glossalearn.link/api/lti/security/jwks",
            
    #         "default": False,
    #         "key_set": None,
    #         "private_key_file": "private.key",
    #         "public_key_file": "public.key",
    #     }]
    # }
    # # we don't need to validate deployment_id since we already verified they were onboarded
    # for iss in configs.keys():
    #     for conf in configs[iss]:
    #         conf["deployment_ids"] = get_all_deployment_ids(deployment_id)
    
    # ASSUMPTION: course is already inserted
    course = get_course(deployment_url, deployment_id)
    deployment_info = get_deployment_info(deployment_url, course['client_id'])
    configs = {
        deployment_url: [{
            
            "client_id": course['client_id'],

            "auth_login_url": deployment_info['auth_login_url'],
            "auth_token_url": deployment_info['auth_token_url'],
            "key_set_url": deployment_info['key_set_url'],
            "deployment_ids": [deployment_id],
            
            "default": False,
            "key_set": None,
        }]
    }


    tool_conf =  ToolConfDict(configs)
    # BUG(upstream): unfortunately the dict path doesn't set the private/public key!
    private_key, public_key = get_private_public_keys()
    for iss, iss_conf in configs.items():
        for iss_conf_item in iss_conf:
            tool_conf.set_private_key(
                iss, private_key, client_id=iss_conf_item["client_id"]
            )
            tool_conf.set_public_key(
                iss, public_key, client_id=iss_conf_item["client_id"]
            )
    return tool_conf

lti_bp = Blueprint('lti', __name__)

class ExtendedFlaskMessageLaunch(FlaskMessageLaunch):

    def validate_nonce(self):
        """
        Probably it is bug on "https://lti-ri.imsglobal.org":
        site passes invalid "nonce" value during deep links launch.
        Because of this in case of iss == http://imsglobal.org just skip nonce validation.

        """
        iss = self.get_iss()
        deep_link_launch = self.is_deep_link_launch()
        if iss == "http://imsglobal.org" and deep_link_launch:
            return self
        # TODO: ignoring nonce for now, why is this not validating?
        return self
        # return super().validate_nonce()

# TODO: refactor this so its not here, this is to avoid a circular dependency
app = Flask(__name__)

# TODO: productionize
config = {
    "DEBUG": True,
    "ENV": "development",
    "CACHE_TYPE": "simple",
    "CACHE_DEFAULT_TIMEOUT": 600,
    "SECRET_KEY": "replace-me",
    "SESSION_TYPE": "filesystem",
    "SESSION_FILE_DIR": mkdtemp(),
    "SESSION_COOKIE_NAME": "pylti1p3-flask-app-sessionid",
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SECURE": False,   # should be True in case of HTTPS usage (production)
    "SESSION_COOKIE_SAMESITE": None,  # should be 'None' in case of HTTPS usage (production)
    "DEBUG_TB_INTERCEPT_REDIRECTS": False
}
app.config.from_mapping(config)
cache = Cache(app)

def get_lti_config_path():
    return os.path.join(app.root_path, 'game.json')


def get_launch_data_storage():
    return FlaskCacheDataStorage(cache)

def register_lti(
    base,
    registration_token,
):
    # TODO: grab from env var
    TOOL_URL = 'nixos.tail3db608.ts.net'
    registration_body = {
        "application_type": "web",
        "client_name": "GlossaLearn",
        "client_uri": f'https://{TOOL_URL}',
        "grant_types": ["client_credentials", "implicit"],

        "jwks_uri": f"https://{TOOL_URL}/jwks/",
        "initiate_login_uri": f"https://{TOOL_URL}/login/",
        "redirect_uris": [f"https://{TOOL_URL}/launch/"],

        "response_types": ["id_token"],
        "scope": "https://purl.imsglobal.org/spec/lti-reg/scope/registration.readonly https://purl.imsglobal.org/spec/lti-reg/scope/registration https://purl.imsglobal.org/spec/lti-ags/scope/lineitem https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly https://purl.imsglobal.org/spec/lti-ags/scope/score https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly https://purl.imsglobal.org/spec/lti/scope/noticehandlers https://canvas.instructure.com/lti/public_jwk/scope/update https://canvas.instructure.com/lti/account_lookup/scope/show https://canvas.instructure.com/lti-ags/progress/scope/show https://canvas.instructure.com/lti/page_content/show",
        "token_endpoint_auth_method": "private_key_jwt",
        "logo_uri": f"https://{TOOL_URL}/icon.svg",

        "https://purl.imsglobal.org/spec/lti-tool-configuration": {
            "claims": [
            # "sub",
            # "iss",
            # "name",
            # "given_name",
            # "family_name",
            # "nickname",
            # "picture",
            # "email",
            # "locale"
            ],
            "custom_parameters": {},
            "domain": TOOL_URL,
            "messages": [
            {
                "type": "LtiResourceLinkRequest",
                "icon_uri": f"https://{TOOL_URL}/icon.svg",
                "label": "GlossaLearn",
                "placements": ["course_navigation"],
                "target_link_uri": f"https://{TOOL_URL}/launch/"
            },
            {
                "type": "LtiResourceLinkRequest",
                "icon_uri": f"https://{TOOL_URL}/icon.svg",
                "placements": ["account_navigation"],
            },
            {
                "type": "LtiResourceLinkRequest",
                "icon_uri": f"https://{TOOL_URL}/icon.svg",
                "label": "GlossaLearn",
                "placements": ["link_selection"],
                "target_link_uri": f"https://TOOL_URL/launch/"
            }
            ],
            "target_link_uri": f"https://{TOOL_URL}/launch/",
            "https://canvas.instructure.com/lti/tool_id": "",
            "https://canvas.instructure.com/lti/privacy_level": "anonymous"
        }
    }
    response = requests.post(
        f'{base}/api/lti/registrations',
        json=registration_body,
        headers={'Authorization': f"Bearer {registration_token}"},
    )

    response.raise_for_status()
    return response.json()['client_id']

def get_openid_configuration(base, registration_token):

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {registration_token}",
    }

    response = requests.get(base, headers=headers, timeout=30)
    response.raise_for_status()

    return response.json()

from urllib.parse import urlsplit

def origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"

@lti_bp.route('/register/', methods=['GET'])
def register():
    openid_conf = request.args.get("openid_configuration")
    registration_token = request.args.get("registration_token")
    base = origin(openid_conf)
    # TODO: reach out to get openid config, for now, assume values
    config_values = get_openid_configuration(openid_conf, registration_token)
    client_id = register_lti(base, registration_token)
    auth_login_url = config_values['authorization_endpoint']
    auth_token_url = config_values['token_endpoint']
    key_set_url = config_values['jwks_uri']
    insert_deployment_info(base, client_id, auth_login_url, auth_token_url, key_set_url)
    return "Tool added! Refresh page and enable!"

@lti_bp.route('/login/', methods=['GET', 'POST'])
def login():
    iss = request.form.get("iss")
    deployment_id = request.form.get("lti_deployment_id")
    client_id = request.form.get("client_id")
    if iss == None:
        iss = origin(request.args.get('iss'))
        deployment_id = request.args.get("lti_deployment_id")
        client_id = request.args.get("client_id")
    insert_course(iss, client_id, deployment_id)
    tool_conf = get_tool_config(iss, deployment_id)
    launch_data_storage = get_launch_data_storage()

    flask_request = FlaskRequest()
    target_link_uri = flask_request.get_param('target_link_uri')
    if not target_link_uri:
        raise Exception('Missing "target_link_uri" param')

    oidc_login = FlaskOIDCLogin(flask_request, tool_conf, launch_data_storage=launch_data_storage)
    return oidc_login\
        .enable_check_cookies()\
        .redirect(target_link_uri)

def get_user(message_launch):
    # this will be slow for large courses, but LTI provides no other way (paging is even slower as many k latencies are paid)
    # also unfortunately nrps makes us join on legacy user id, as no non legacy user id is sent during launch
    message_launch_data = message_launch.get_launch_data()
    user_id = message_launch_data.get('https://purl.imsglobal.org/spec/lti/claim/lti11_legacy_user_id', '')
    current_user = [user for user in message_launch.get_nrps().get_members() if user.get('lti11_legacy_user_id', '').replace('-', '') == user_id]
    if len(current_user) != 1:
        return None
    cUser = current_user[0]
    if not cUser:
        print("cUsr", cUser)
    return cUser

def eval_is_student(current_user):
    return not current_user or 'http://purl.imsglobal.org/vocab/lis/v2/membership#Learner' in current_user['roles']

@lti_bp.post('/launch/')
def launch():
    # directly decode jwt to get deployment_url, deployment_id
    # this is safe, since we still validate before doing anything
    id_token = request.form.get('id_token')
    jwt_parts = id_token.split(".")
    body = json.loads(FlaskMessageLaunch.urlsafe_b64decode(jwt_parts[1]))
    
    deployment_url = body['iss']
    deployment_id = body['https://purl.imsglobal.org/spec/lti/claim/deployment_id']
    tool_conf = get_tool_config(deployment_url, deployment_id)
    flask_request = FlaskRequest()
    launch_data_storage = get_launch_data_storage()
    message_launch = ExtendedFlaskMessageLaunch(flask_request, tool_conf, launch_data_storage=launch_data_storage)
    
    current_user = get_user(message_launch)
    is_student = str(eval_is_student(current_user))
    return redirect(f'{DEPLOYMENT_URL}/?is_student={is_student}&launch_id={message_launch.get_launch_id()}&deployment_id={deployment_id}&deployment_url={deployment_url}')

def get_public_keys():
    # TODO: actually get these
    return [PUBLIC_KEY]

@lti_bp.get('/jwks/')
def get_jwks():
    return jsonify({'keys': {"keys": [Registration.get_jwk(k) for k in get_public_keys()]}})

def get_deployment_user_id(message_launch):
    launch_data = message_launch.get_launch_data()
    return (launch_data.get('https://purl.imsglobal.org/spec/lti/claim/deployment_id', ''), launch_data.get('https://purl.imsglobal.org/spec/lti/claim/lti1p1', {}).get('user_id', ''))

# TODO: should be middleware, as with many other things, refactor later
def get_message_launch_and_gate_nonusers(launch_id, args, teacher_only=False):
    deployment_url = args.get('deployment_url')
    deployment_id = args.get('deployment_id')
    try:
        tool_conf = get_tool_config(deployment_url, deployment_id)
        flask_request = FlaskRequest()
        launch_data_storage = get_launch_data_storage()
        message_launch = ExtendedFlaskMessageLaunch.from_cache(launch_id, flask_request, tool_conf,
                                                            launch_data_storage=launch_data_storage)
        current_user = get_user(message_launch)
        # technically covered by below case, but going to leave this explicit
        if not current_user:
            print("no user?")
            abort(403)
        if teacher_only and eval_is_student(current_user):
            print("teachers only")
            abort(403)
        return (message_launch, current_user)
    except LtiException as e:
        # HACK:
        # okay so we depend on cached launch_id
        # due to oauth flow, we need multiple workers otherwise we guaranteed deadlock
        # honestly we need way more than 2 workers otherwise we will deadlock frequently in prod
        # anyways cache is not shared (in memory, isolated per process)
        # we should be storing session information in redis or the like
        # if somehow a user hits this case when we are using redis, their entire page should reload to "flush" the old launch_id
        # so an extremely hacky solution to this eisenbug is to send back teapot error and have the frontend retry requests 10 times if they 418
        # this drops frontend realized errors from 50% to ~.1%
        abort(418)

# AUTHORIZATION:
# if we cannot get a user, we are not in the course and thus not authorized
# if we are a student, then we cannot use any teacher method

# i feel mixed about launch_id containing so much information
interactive_bp = Blueprint('interactive', __name__)
@interactive_bp.get("/assignments/<launch_id>")
def get_assignments(launch_id):
    message_launch, _ = get_message_launch_and_gate_nonusers(launch_id, request.args)
    deployment_id, _ = get_deployment_user_id(message_launch)
    query = """
        SELECT
            deployment_id,
            assignment_id,
            assignment_type,
            created_at,
            author,
            work,
            sentence_id
        FROM assignment
        WHERE deployment_id = %s
        ORDER BY created_at DESC;
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (deployment_id,))
            rows = cur.fetchall()

    assignments = []

    for row in rows:
        assignments.append({
            "deployment_id": row[0],
            "assignment_id": row[1],
            "assignment_type": row[2],
            "created_at": row[3].isoformat(),
            "author": row[4],
            "work": row[5],
            "sentence_id": row[6]
        })

    return jsonify(assignments)

# TODO: we infer if they want their own submissions or all submissions based off of launch_id (proxy of jwt)
# we should instead break this into two different endpoints
@interactive_bp.get("/submissions/<launch_id>")
def get_submissions(launch_id):
    message_launch, current_user = get_message_launch_and_gate_nonusers(launch_id, request.args)
    deployment_id, user_id = get_deployment_user_id(message_launch)
    student_id = '' if not eval_is_student(current_user) else user_id
    query = """
        SELECT
            deployment_id,
            assignment_id,
            student_id,
            assignment_artifact,
            grade,
            created_at
        FROM assignment_submission
        WHERE deployment_id = %s """ + f"{'' if not student_id else 'and student_id = %s'}\n" + "ORDER BY created_at DESC;\n"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (deployment_id,) if not student_id else (deployment_id,student_id))
            rows = cur.fetchall()

    submissions = []

    for row in rows:
        submissions.append({
            "deployment_id": row[0],
            "assignment_id": row[1],
            "student_id": row[2],
            "assignment_artifact": row[3],
            "grade": float(row[4]) if row[4] is not None else None,
            "created_at": row[5].isoformat()
        })

    return jsonify(submissions)

@interactive_bp.post("/assignment/<launch_id>")
def create_assignment(launch_id):
    message_launch, _ = get_message_launch_and_gate_nonusers(launch_id, request.args, teacher_only=True)
    deployment_id, _ = get_deployment_user_id(message_launch)
    body = request.get_json()

    query = """
        INSERT INTO assignment (
            deployment_id,
            deployment_url,
            assignment_id,
            assignment_type,
            author,
            work,
            sentence_id
        )
        VALUES (
            %s,
            %s,
            %s,
            %s, %s, %s, %s
        )
        RETURNING assignment_id;
    """

    values = (
        deployment_id,
        request.args['deployment_url'],
        body["assignment_id"],
        body["assignment_type"],
        body["author"],
        body["work"],
        body["sentence_id"]
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, values)
            row = cur.fetchone()

        conn.commit()

    return jsonify({
        "status": "created",
        "assignment_id": row[0]
    }), 201

# TODO: unify create/submit submission via upsert
@interactive_bp.post("/submission/<launch_id>")
def create_submission(launch_id):
    message_launch, _ = get_message_launch_and_gate_nonusers(launch_id, request.args)
    body = request.get_json()
    deployment_id, _ = get_deployment_user_id(message_launch)
    
    # the id for the grading service is not actually either user_id or legacy_user_id, but none other than sub
    student_id = message_launch.get_launch_data().get('sub')
    # ON CONFLICT DO UPDATE "upserts"
    query = """
        INSERT INTO assignment_submission (
            deployment_id,
            deployment_url,
            assignment_id,
            student_id,
            assignment_artifact
        )
        VALUES (
            %s,
            %s,
            %s, %s,
            %s
        )
        ON CONFLICT (
            deployment_id,
            assignment_id,
            student_id
        )
        DO UPDATE
        SET assignment_artifact = EXCLUDED.assignment_artifact
        RETURNING
            deployment_id;
    """

    values = (
        deployment_id,
        request.args['deployment_url'],
        body["assignment_id"],
        student_id,
        body["assignment_artifact"],
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, values)
            row = cur.fetchone()

        conn.commit()

    return jsonify({
        "status": "created",
        "deployment_id": row[0],
    }), 201

@interactive_bp.post("/submission/<launch_id>/submit")
def submit_submission(launch_id):

    message_launch, _ = get_message_launch_and_gate_nonusers(launch_id, request.args)
    body = request.get_json()
    deployment_id, _ = get_deployment_user_id(message_launch)
    student_id = message_launch.get_launch_data().get('sub')
    query = """
        UPDATE assignment_submission
        SET assignment_artifact = %s
        WHERE
            deployment_id = %s
            AND assignment_id = %s
            AND student_id = %s
            RETURNING 1;
    """

    values = (
        body["assignment_artifact"],
        deployment_id,
        body["assignment_id"],
        student_id
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, values)
            row = cur.fetchone()

        conn.commit()

    if row is None:
        return jsonify({"error": "submission not found"}), 404

    return jsonify({
        "status": "submitted",
    })

@interactive_bp.post("/submission/<launch_id>/grade")
def grade_submission(launch_id):

    message_launch, _ = get_message_launch_and_gate_nonusers(launch_id, request.args, teacher_only=True)
    body = request.get_json()
    deployment_id, _ = get_deployment_user_id(message_launch)

    query = """
        UPDATE assignment_submission
        SET grade = %s
        WHERE
            deployment_id = %s
            AND assignment_id = %s
            AND student_id = %s
        RETURNING grade;
    """
    values = (
        body["grade"],
        deployment_id,
        body["assignment_id"],
        body["student_id"],
    )

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, values)
            row = cur.fetchone()

        conn.commit()

    if row is None:
        return jsonify({"error": "submission not found"}), 404
    
    resource_link_id = message_launch.get_launch_data() \
        .get('https://purl.imsglobal.org/spec/lti/claim/resource_link', {}).get('id')
    
    grades = message_launch.get_ags()
    sc = Grade()
    sc.set_score_given(body["grade"]) \
        .set_score_maximum(100) \
        .set_timestamp(datetime.datetime.utcnow().isoformat() + 'Z') \
        .set_activity_progress('Completed') \
        .set_grading_progress('FullyGraded') \
        .set_user_id(body["student_id"])

    sc_line_item = LineItem()
    sc_line_item.set_tag('score') \
        .set_score_maximum(100) \
        .set_label('Score')
    if resource_link_id:
        sc_line_item.set_resource_id(resource_link_id)

    grades.put_grade(sc, sc_line_item)

    return jsonify({
        "status": "graded",
        "grade": float(row[0])
    })