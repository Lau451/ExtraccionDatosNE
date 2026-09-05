from typing import Any

from supabase import Client

# -- tercero_direcciones -------------------------------------------------------


def crear_direccion(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("tercero_direcciones").insert(fila).execute().data[0]


def buscar_direccion(client: Client, *, direccion_id: str) -> dict[str, Any] | None:
    resultado = (
        client.table("tercero_direcciones").select("*").eq("id", direccion_id).limit(1).execute()
    )
    return resultado.data[0] if resultado.data else None


def listar_direcciones(
    client: Client,
    *,
    tercero_id: str,
    drogueria_id: str,
    activo: bool | None = None,
    uso: str | None = None,
) -> list[dict[str, Any]]:
    if uso is not None:
        # Filtrar por uso exige pasar por la tabla puente direccion_usos: no hay
        # columna de uso en tercero_direcciones (es N:M, ver design.md sección 3).
        # direccion_usos tiene dos FK hacia tercero_direcciones (fk_du_dir_drog y
        # fk_du_dir_tercero, ambas sobre id) -- PostgREST exige desambiguar cuál
        # relación embeber (PGRST201) o falla con "more than one relationship".
        resultado = (
            client.table("direccion_usos")
            .select("tercero_direcciones!fk_du_dir_tercero(*)")
            .eq("tercero_id", tercero_id)
            .eq("drogueria_id", drogueria_id)
            .eq("uso", uso)
            .execute()
        )
        direcciones = [
            fila["tercero_direcciones"]
            for fila in resultado.data
            if fila.get("tercero_direcciones") is not None
        ]
        if activo is not None:
            direcciones = [d for d in direcciones if d["activo"] == activo]
        return direcciones

    query = (
        client.table("tercero_direcciones")
        .select("*")
        .eq("tercero_id", tercero_id)
        .eq("drogueria_id", drogueria_id)
    )
    if activo is not None:
        query = query.eq("activo", activo)
    return query.order("created_at").execute().data


def actualizar_direccion(
    client: Client, *, direccion_id: str, campos: dict[str, Any]
) -> dict[str, Any]:
    return (
        client.table("tercero_direcciones")
        .update(campos)
        .eq("id", direccion_id)
        .execute()
        .data[0]
    )


def eliminar_direccion(client: Client, *, direccion_id: str) -> None:
    # fk_du_dir_drog/fk_du_dir_tercero llevan ON DELETE CASCADE (0008_terceros_modelo.sql,
    # sección 3): borrar la dirección arrastra sus direccion_usos sin necesidad de un
    # segundo DELETE.
    client.table("tercero_direcciones").delete().eq("id", direccion_id).execute()


# -- direccion_usos --------------------------------------------------------------


def crear_uso(client: Client, fila: dict[str, Any]) -> dict[str, Any]:
    return client.table("direccion_usos").insert(fila).execute().data[0]


def listar_usos(client: Client, *, direccion_id: str) -> list[dict[str, Any]]:
    return (
        client.table("direccion_usos")
        .select("*")
        .eq("direccion_id", direccion_id)
        .order("uso")
        .execute()
        .data
    )


def eliminar_uso(client: Client, *, direccion_id: str, uso: str) -> None:
    client.table("direccion_usos").delete().eq("direccion_id", direccion_id).eq(
        "uso", uso
    ).execute()
