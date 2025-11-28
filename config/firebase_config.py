# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Optional, Dict
import os
import firebase_admin
from firebase_admin import credentials, firestore
from config.default import Default


class FirebaseClient:
    """Firestore client manager supporting multiple database IDs.

    This avoids binding the entire process to the first database requested.
    It caches a client per database_id and initializes firebase_admin once.
    """

    _app_initialized: bool = False
    _clients: Dict[str, firestore.Client] = {}

    def __init__(self, database_id: Optional[str] = None):
        # Default Firestore database id when not provided
        self._database_id = database_id or "(default)"
        if not FirebaseClient._app_initialized:
            try:
                # Ensure project id is available to google.auth.default to avoid gcloud subprocess calls
                project_id = Default().PROJECT_ID
                if project_id:
                    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
                    os.environ.setdefault("GCP_PROJECT", project_id)
                cred = credentials.ApplicationDefault()
                # Initialize with explicit project to avoid ADC project drift.
                firebase_admin.initialize_app(cred, {"projectId": project_id})
            except ValueError:
                # Already initialized elsewhere
                pass
            FirebaseClient._app_initialized = True

    def get_client(self) -> firestore.Client:
        # Return cached client or create a new one for this database id
        db_id = self._database_id
        client = FirebaseClient._clients.get(db_id)
        if client is None:
            # Use database_id for the installed firebase_admin version and rely on initialize_app(projectId=...).
            client = firestore.client(database_id=db_id)
            FirebaseClient._clients[db_id] = client
        return client
