# Guion UGC — detalle, ejemplos y prompt

## Recordatorio de la fórmula

30–60 segundos, 5 partes con timing: **gancho (0–3s) → problema (4–12s) →
solución (13–35s) → prueba (36–48s) → CTA (final)**. Primera persona, tono de
persona común, beneficios y no características, cierre con urgencia/escasez.

## Ejemplo completo (producto: relleno para asientos de carro)

Este es el tipo de guion que buscamos: arranca por el dolor, no por el producto.

> **Gancho (0–3s):** No saben el odio que le tenía a este hueco hasta hace una
> semana. Mira esto.
>
> **Problema (4–12s):** Cada vez que me subía al carro se me caían las llaves,
> las monedas del peaje… El celular una vez se me cayó y tuve que parar en plena
> vía a sacarlo. La última vez perdí 50.000 pesos en monedas que se fueron por
> aquí abajo. Y lo peor: para sacarlo tienes que bajarte, mover el asiento,
> meter la mano, contorsionarte. Una pesadilla…
>
> **Solución (13–35s):** …hasta que me llegó esto. Es un relleno para asientos.
> Mira lo fácil: lo metes así, encaja perfecto entre el asiento y la consola y
> se acabó el problema. Ya no se cae absolutamente nada — monedas, llaves,
> celular, todo se queda arriba. Es como tener un mini bolsillo extra dentro del
> carro. Y lo mejor: está hecho de un material suave, no raya el cuero del
> asiento y se quita en 2 segundos si necesitas limpiarlo.
>
> **Prueba (36–48s):** Llevo una semana usándolo todos los días — ida y vuelta
> al trabajo, fines de semana, viajes — y nunca más se me cayó nada. En serio,
> debí comprarlo hace años.
>
> **CTA (final):** Ahora mismo está en oferta 2 por 1: sí, llevas dos por el
> precio de uno. Uno para tu carro y otro para regalárselo a alguien que también
> tenga el problema o ponerlo en el carro de tu pareja. Te dejo el link en la
> descripción, pero apúrate porque la oferta no dura mucho y se está acabando el
> stock. Yo ya pedí dos.

Nota cómo el gancho y el problema ocupan casi la mitad del guion: eso es lo que
retiene. El producto aparece recién en el segundo ~13.

## Beneficios, no características

Traduce siempre la ficha técnica a lo que la persona siente:

| No digas (característica) | Di (beneficio) |
|---|---|
| Batería de 5.000 mAh | Te dura hasta 3 días sin cargar |
| Ácido hialurónico al 2% | Te ves 5 años más joven |
| Material de silicona antideslizante | Ya no se te cae absolutamente nada |
| 1.200 W de potencia | Listo en la mitad del tiempo |

## Ganchos que funcionan

- **Verbal de dolor:** "No saben el odio que le tenía a este hueco…".
- **Formato noticia:** un titular tipo "Conductor se enoja con su carro por
  esto". La gente es curiosa y entra a ver qué pasó. Muy útil como primer plano.
- **Visual brusco / inesperado:** un plano raro o gracioso que obliga a frenar
  el scroll.
- **Pregunta abierta:** algo que deje al espectador con una duda que solo se
  resuelve viendo más.

## Prompt reutilizable para generar guiones

Cuando el usuario quiera generar varios guiones (o cuando tú los generes),
apóyate en este encuadre. Está entrenado para que **suenen reales, no a
comercial de televisión**:

```
Eres un guionista experto en anuncios UGC de respuesta directa para
e-commerce/dropshipping. Escribe un guion para un anuncio de 30–60 segundos
del siguiente producto.

Producto: [nombre + qué hace + qué problema resuelve]
Mercado/país: [ej. Colombia — usa modismos y moneda locales]
Oferta: [ej. 2x1 + envío gratis]

Reglas:
- Primera persona, tono de persona común contando su experiencia real. NADA de
  locución de comercial ni de listar características técnicas.
- Estructura en 5 partes con su timing marcado: Gancho (0–3s), Problema
  (4–12s), Solución (13–35s), Prueba (36–48s), CTA (final).
- Arranca por el dolor, no por el producto. El producto aparece recién en la
  solución.
- Traduce toda característica a un beneficio sensorial/emocional.
- Cierra con un CTA con urgencia o escasez concreta.

Entrega dos versiones:
1) El texto corrido (para pegar en ElevenLabs, sin encabezados).
2) El mismo guion segmentado por las 5 partes con su timing (para editar).
```

Para escalar, genera **5 guiones distintos** del mismo producto variando el
ángulo (dolor distinto, gancho distinto, formato noticia vs. testimonio, etc.).
Ver `escalado.md`.
