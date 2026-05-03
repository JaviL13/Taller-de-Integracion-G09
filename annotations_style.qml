<!-- Este es un documento de estilo para QGIS -->
<!-- Este será usado como respaldo en caso de que el Raster no esté disponible -->

<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.16" styleCategories="Symbology">
  <renderer-v2 type="categorizedSymbol" attr="status" forceraster="0">
    <categories>

      <!-- Categoría pending: naranja con transparencia -->
      <category value="pending" label="pending" render="true">
        <symbol type="fill" name="pending" clip_to_extent="1">
          <layer class="SimpleFill">
            <!-- Color naranja RGBA: 243, 156, 18, 100 -->
            <!-- El último valor (100) corresponde a la transparencia, es el 100 sobre 225 -->
            <Option type="Map">
              <Option name="color" value="243,156,18,100" type="QString"/>
              <Option name="style" value="solid" type="QString"/>
              <Option name="outline_color" value="243,156,18,255" type="QString"/>
              <Option name="outline_width" value="0.5" type="QString"/>
            </Option>
          </layer>
        </symbol>
      </category>

      <!-- Categoría approved: verde con transparencia -->
      <category value="approved" label="approved" render="true">
        <symbol type="fill" name="approved" clip_to_extent="1">
          <layer class="SimpleFill">
            <!-- Color verde RGBA: 39, 174, 96, 100 -->
            <Option type="Map">
              <Option name="color" value="39,174,96,100" type="QString"/>
              <Option name="style" value="solid" type="QString"/>
              <Option name="outline_color" value="39,174,96,255" type="QString"/>
              <Option name="outline_width" value="0.5" type="QString"/>
            </Option>
          </layer>
        </symbol>
      </category>

      <!-- Categoría rejected: rojo con transparencia -->
      <category value="rejected" label="rejected" render="true">
        <symbol type="fill" name="rejected" clip_to_extent="1">
          <layer class="SimpleFill">
            <!-- Color rojo RGBA: 231, 76, 60, 100 -->
            <Option type="Map">
              <Option name="color" value="231,76,60,100" type="QString"/>
              <Option name="style" value="solid" type="QString"/>
              <Option name="outline_color" value="231,76,60,255" type="QString"/>
              <Option name="outline_width" value="0.5" type="QString"/>
            </Option>
          </layer>
        </symbol>
      </category>

    </categories>
  </renderer-v2>
</qgis>