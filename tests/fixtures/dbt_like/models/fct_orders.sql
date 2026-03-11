SELECT u.id, e.amount
FROM {{ ref('stg_users') }} u
JOIN {{ source('raw','events') }} e ON u.id = e.user_id
