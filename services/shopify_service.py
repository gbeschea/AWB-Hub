import httpx
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from settings import ShopifyStore


async def fetch_orders_graphql(store: ShopifyStore, since_days: int) -> List[Dict[str, Any]]:
    """Prelucrează comenzile folosind API-ul GraphQL pentru date mai precise."""
    api_version = store.api_version
    domain = store.domain
    token = store.access_token
    url = f"https://{domain}/admin/api/{api_version}/graphql.json"
    headers = {'X-Shopify-Access-Token': token, 'Content-Type': 'application/json'}

    created_at_min = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()

    # --- START MODIFICATION ---
    # Am eliminat toate filtrele de status, lăsând doar filtrul de dată.
    # Aceasta este cea mai inclusivă interogare posibilă.
    api_query_string = f"created_at:>{created_at_min}"
    # --- END MODIFICATION ---

    query = """
    query($first: Int!, $query: String, $cursor: String) {
      orders(first: $first, query: $query, after: $cursor, sortKey: CREATED_AT, reverse: false) {
        pageInfo { hasNextPage, endCursor }
        edges {
          node {
            id, name, createdAt, tags, note,
            cancelledAt,
            displayFinancialStatus,
            displayFulfillmentStatus,
            totalPriceSet { shopMoney { amount } },
            paymentGatewayNames,
            shippingAddress { name, address1, address2, phone, city, zip, province, country },
            lineItems(first: 20) { edges { node { sku, title, quantity } } },
            fulfillments(first: 5) {
              id, status,
              trackingInfo { company, number, url },
              createdAt,
              updatedAt
            },
            fulfillmentOrders(first: 5) {
              edges {
                node { id, status, fulfillmentHolds { reason, reasonNotes } }
              }
            }
          }
        }
      }
    }
    """

    all_orders = []
    has_next_page = True
    cursor = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        while has_next_page:
            variables = { "first": 100, "query": api_query_string, "cursor": cursor }
            try:
                r = await client.post(url, json={'query': query, 'variables': variables}, headers=headers)
                r.raise_for_status()
                data = r.json()

                if "errors" in data:
                    logging.error(f"Eroare GraphQL pentru {domain}: {data['errors']}")
                    break

                orders_data = data.get("data", {}).get("orders", {})
                for edge in orders_data.get("edges", []):
                    all_orders.append(edge["node"])

                page_info = orders_data.get("pageInfo", {})
                has_next_page = page_info.get("hasNextPage", False)
                cursor = page_info.get("endCursor")

            except httpx.HTTPStatusError as e:
                logging.error(f"Eroare API Shopify (GraphQL) pentru {domain}: {e.response.status_code} - {e.response.text}")
                break
            except Exception as e:
                logging.error(f"Excepție neașteptată la preluarea comenzilor GraphQL pentru {domain}: {e}", exc_info=True)
                break

    return all_orders

fetch_orders = fetch_orders_graphql

async def get_open_fulfillment_order_id(store_cfg: ShopifyStore, order_gid: str) -> Optional[str]:
    """Interoghează Shopify pentru a găsi ID-ul primului FulfillmentOrder deschis."""
    api_version = store_cfg.api_version
    url = f"https://{store_cfg.domain}/admin/api/{api_version}/graphql.json"
    headers = {'X-Shopify-Access-Token': store_cfg.access_token, 'Content-Type': 'application/json'}
    
    query = """
    query GetFFOrders($id: ID!) { 
      order(id: $id) { 
        fulfillmentOrders(first: 5, query: "status:open") { 
          edges { node { id } } 
        } 
      } 
    }
    """
    body = {"query": query, "variables": {"id": order_gid}}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            fulfillment_orders = r.json().get("data", {}).get("order", {}).get("fulfillmentOrders", {}).get("edges", [])
            if not fulfillment_orders:
                logging.warning(f"Niciun FulfillmentOrder deschis găsit pentru comanda {order_gid}.")
                return None
            return fulfillment_orders[0]['node']['id']
        except Exception as e:
            logging.error(f"Excepție la găsirea FulfillmentOrder pentru {order_gid}: {e}", exc_info=True)
            return None

async def hold_fulfillment_order(store_cfg: ShopifyStore, fulfillment_order_id: str) -> bool:
    """Apelează mutația GraphQL pentru a pune un FulfillmentOrder pe 'hold'."""
    api_version = store_cfg.api_version
    url = f"https://{store_cfg.domain}/admin/api/{api_version}/graphql.json"
    headers = {'X-Shopify-Access-Token': store_cfg.access_token, 'Content-Type': 'application/json'}
    
    mutation = """
    mutation fulfillmentOrderHold($id: ID!) {
      fulfillmentOrderHold(id: $id) {
        fulfillmentOrder {
          id
          status
        }
        userErrors {
          field
          message
        }
      }
    }
    """
    body = {"query": mutation, "variables": {"id": fulfillment_order_id}}

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            response_data = r.json()
            user_errors = response_data.get("data", {}).get("fulfillmentOrderHold", {}).get("userErrors", [])
            if user_errors:
                logging.error(f"Eroare la punerea pe hold a {fulfillment_order_id}: {user_errors}")
                return False
            logging.info(f"FulfillmentOrder {fulfillment_order_id} a fost pus pe hold cu succes.")
            return True
        except Exception as e:
            logging.error(f"Excepție la punerea pe hold a {fulfillment_order_id}: {e}", exc_info=True)
            return False

async def _update_existing_fulfillment(store_cfg: ShopifyStore, fulfillment_gid: str, tracking_info: Dict[str, str]) -> bool:
    logging.info(f"Crearea unui eveniment 'LABEL_PRINTED' pentru fulfillment-ul: {fulfillment_gid}")
    api_version = store_cfg.api_version
    url = f"https://{store_cfg.domain}/admin/api/{api_version}/graphql.json"
    headers = {'X-Shopify-Access-Token': store_cfg.access_token, 'Content-Type': 'application/json'}
    mutation = """
    mutation fulfillmentEventCreate($fulfillmentEvent: FulfillmentEventInput!) {
      fulfillmentEventCreate(fulfillmentEvent: $fulfillmentEvent) {
        fulfillmentEvent { id, status }
        userErrors { field, message }
      }
    }
    """
    variables = { "fulfillmentEvent": { "fulfillmentId": fulfillment_gid, "status": "LABEL_PRINTED", "happenedAt": datetime.now(timezone.utc).isoformat() } }
    body = {"query": mutation, "variables": variables}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.post(url, json=body, headers=headers)
            r.raise_for_status()
            response_data = r.json()
            if 'errors' in response_data:
                logging.error(f"Eroare GraphQL de la Shopify pentru fulfillment {fulfillment_gid}: {response_data['errors']}")
                return False
            data = response_data.get("data")
            if not data:
                logging.warning(f"Răspunsul de la Shopify pentru {fulfillment_gid} nu conține 'data'. Răspuns: {response_data}")
                return False
            fulfillment_event_create = data.get("fulfillmentEventCreate")
            if not fulfillment_event_create:
                logging.warning(f"Răspunsul pentru {fulfillment_gid} nu conține 'fulfillmentEventCreate', posibil deja procesat. Răspuns: {data}")
                return True
            user_errors = fulfillment_event_create.get("userErrors", [])
            if user_errors:
                logging.error(f"Eroare la crearea evenimentului pentru fulfillment {fulfillment_gid}: {user_errors}")
                return False
            logging.info(f"Eveniment 'LABEL_PRINTED' creat cu succes pentru fulfillment-ul {fulfillment_gid}.")
            return True
        except Exception as e:
            logging.error(f"Excepție la crearea evenimentului pentru fulfillment {fulfillment_gid}: {e}", exc_info=True)
            return False

async def _create_fulfillment_from_order(store_cfg: ShopifyStore, order_gid: str, tracking_info: Dict[str, str]) -> bool:
    logging.info(f"Încercare de a crea un fulfillment nou pentru comanda: {order_gid}")
    api_version = store_cfg.api_version
    url = f"https://{store_cfg.domain}/admin/api/{api_version}/graphql.json"
    headers = {'X-Shopify-Access-Token': store_cfg.access_token, 'Content-Type': 'application/json'}
    get_ff_order_query = """
    query GetFFOrders($id: ID!) { order(id: $id) { fulfillmentOrders(first: 5, query: "status:open") { edges { node { id } } } } }
    """
    body_step1 = {"query": get_ff_order_query, "variables": {"id": order_gid}}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.post(url, json=body_step1, headers=headers)
            r.raise_for_status()
            fulfillment_orders = r.json().get("data", {}).get("order", {}).get("fulfillmentOrders", {}).get("edges", [])
            if not fulfillment_orders:
                logging.warning(f"Niciun FulfillmentOrder deschis găsit pentru comanda {order_gid}.")
                return False
            fulfillment_order_id = fulfillment_orders[0]['node']['id']
        except Exception as e:
            logging.error(f"Excepție la găsirea FulfillmentOrder pentru {order_gid}: {e}", exc_info=True)
            return False
    create_ff_mutation = """
    mutation fulfillmentCreateV2($fulfillment: FulfillmentV2Input!) {
      fulfillmentCreateV2(fulfillment: $fulfillment) {
        fulfillment { id, status }
        userErrors { field, message }
      }
    }
    """
    variables_step2 = { "fulfillment": { "notifyCustomer": False, "trackingInfo": tracking_info, "lineItemsByFulfillmentOrder": [{"fulfillmentOrderId": fulfillment_order_id}] } }
    body_step2 = {"query": create_ff_mutation, "variables": variables_step2}
    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            r = await client.post(url, json=body_step2, headers=headers)
            r.raise_for_status()
            user_errors = r.json().get("data", {}).get("fulfillmentCreateV2", {}).get("userErrors", [])
            if user_errors:
                logging.error(f"Eroare la crearea fulfillment-ului pentru {order_gid}: {user_errors}")
                return False
            logging.info(f"Fulfillment creat cu succes pentru comanda {order_gid}.")
            return True
        except Exception as e:
            logging.error(f"Excepție la crearea fulfillment-ului pentru {order_gid}: {e}", exc_info=True)
            return False

async def notify_shopify_of_shipment(store_cfg: ShopifyStore, order_gid: str, fulfillment_id: Optional[str], tracking_info: Dict[str, str]) -> bool:
    if fulfillment_id:
        fulfillment_gid = f"gid://shopify/Fulfillment/{fulfillment_id}"
        return await _update_existing_fulfillment(store_cfg, fulfillment_gid, tracking_info)
    else:
        return await _create_fulfillment_from_order(store_cfg, order_gid, tracking_info)