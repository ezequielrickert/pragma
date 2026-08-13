# Generated from recorded interaction traces. Every Given/When/Then is rendered from what the
# crawl observed - the model was asked only for scenario titles, never for a step, so each line
# asserts what happened rather than what plausibly might have.
#
# These describe what CAN be done rather than what a user sets out to do: the crawl is
# exhaustive, not goal-directed, and a pass ends the moment an interaction navigates - which is
# also what makes that cut a natural scenario boundary.

Feature: www.empanad.app

  Scenario: click Copiar link on empanad.app/o/msUc9nBw6jBAfSUQPW-8y-dNEMtdMsD5
    Given the user is on "empanad.app/o/{token}"
    When the user clicks "Copiar link"
    And the user clicks "Invitar por WhatsApp"
    And the user clicks "Agregar"
    And the user clicks "Agregar"
    And the user clicks "Agregar"
    And the user clicks "Agregar"
    And the user clicks "Agregar variedad"
    And the user clicks "Detalle por persona"
    And the user clicks "Agregar pedido de alguien más"
    And the user clicks "EmpanadApp"
    Then the response to POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections is 201
    And the response to POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections is 201
    And the response to POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections is 201
    And the response to POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections is 201
    And the response to POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders is 201
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors is 200
    And the client sends GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections
    And the client sends GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants
    And the user is on "empanad.app/o/msUc9nBw6jBAfSUQPW-8y-dNEMtdMsD5"

  Scenario: click Restar on empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWSw5xxNx
    Given the user is on "empanad.app/o/{token}"
    When the user clicks "Restar"
    And the user clicks "Sumar"
    And the user clicks "Restar"
    And the user clicks "Sumar"
    And the user clicks "Restar"
    And the user clicks "Sumar"
    And the user clicks "Restar"
    And the user clicks "Sumar"
    And the user enters "1" into "text field (number)"
    Then the response to DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections is 204
    And the response to DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections is 204
    And the response to DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections is 204
    And the response to DELETE https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections is 204
    And the user is on "empanad.app/o/fCsz9xV3-3iDYqP_pa-yDcGWWSw5xxNx"

  Scenario: fill text field (text) on empanad.app/o/twT7V1HfIhAria0JIz1kzC9kezoVNzU-
    Given the user is on "empanad.app/o/{token}"
    When the user enters "María" into "text field (text)"
    And the user clicks "Otra / No sé"
    And the user clicks "Unirte al pedido"
    And the user clicks "EmpanadApp"
    Then the response to POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants is 201
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants is 200
    And the response to POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders is 201
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants is 200
    And the user is on "empanad.app/o/twT7V1HfIhAria0JIz1kzC9kezoVNzU-"

  Scenario: click EmpanadApp on empanad.app/o/naLAQ0Uysf0SjgW0JSeZj5ne0meo96rV
    Given the user is on "empanad.app/o/{token}"
    When the user clicks "EmpanadApp"
    Then the response to POST https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders is 201
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/orders is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/global_flavors is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/order_custom_flavors is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participant_selections is 200
    And the response to GET https://obvwnqnvzifrzyklvqdf.supabase.co/rest/v1/participants is 200
    And the user is on "empanad.app/o/naLAQ0Uysf0SjgW0JSeZj5ne0meo96rV"
